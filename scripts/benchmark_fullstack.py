"""Run concurrent full-stack SHSD analysis and write JSON/Markdown measurements.

Examples::

    python scripts/benchmark_fullstack.py --streams 2 5 --cycles 1
    python scripts/benchmark_fullstack.py --streams 5 --duration-minutes 5

Every cycle launches one independent CLI analyzer per stream. ``--cycles`` is
intended for short scale checks; ``--duration-minutes`` repeats cycles until the
requested wall time has elapsed, for sustained replay soak runs.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "tests" / "fixtures" / "media" / "av_sync_20s.mp4"
DEFAULT_REPORT_DIR = ROOT / "benchmarks" / "reports"


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil((percentile / 100) * len(ordered)) - 1)
    return round(ordered[index], 3)


def _summary(values: list[float], *, unit: str) -> dict[str, float | int | None]:
    if not values:
        return {
            "sample_count": 0,
            f"mean_{unit}": None,
            f"p50_{unit}": None,
            f"p95_{unit}": None,
            f"max_{unit}": None,
        }
    return {
        "sample_count": len(values),
        f"mean_{unit}": round(statistics.fmean(values), 3),
        f"p50_{unit}": _percentile(values, 50),
        f"p95_{unit}": _percentile(values, 95),
        f"max_{unit}": round(max(values), 3),
    }


class _DiskQueueSampler:
    """Best-effort sampler for the Windows physical-disk queue depth counter."""

    counter_path = r"\PhysicalDisk(_Total)\Current Disk Queue Length"

    def __init__(self) -> None:
        self._pdh: Any | None = None
        self._query: Any | None = None
        self._counter: Any | None = None
        self.counter_type: int | None = None
        self.error: str | None = None
        self.samples: list[float] = []
        if sys.platform != "win32":
            self.error = "Windows PDH counters are only available on Windows"
            return
        try:
            import win32pdh

            self._pdh = win32pdh
            self._query = win32pdh.OpenQuery()
            self._counter = win32pdh.AddEnglishCounter(self._query, self.counter_path)
            # PDH needs an initial sample before a formatted value can be read.
            win32pdh.CollectQueryData(self._query)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.close()

    @property
    def available(self) -> bool:
        return self._pdh is not None and self._query is not None and self._counter is not None

    def sample(self) -> float | None:
        if not self.available:
            return None
        try:
            self._pdh.CollectQueryData(self._query)
            counter_type, value = self._pdh.GetFormattedCounterValue(
                self._counter, self._pdh.PDH_FMT_DOUBLE
            )
            self.counter_type = int(counter_type)
            value = float(value)
            if math.isfinite(value) and value >= 0:
                self.samples.append(value)
                return value
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.close()
        return None

    def close(self) -> None:
        if self._pdh is not None and self._query is not None:
            try:
                self._pdh.CloseQuery(self._query)
            except Exception:
                pass
        self._query = None
        self._counter = None
        self._pdh = None


def _process_tree(root_pid: int) -> list[psutil.Process]:
    try:
        root = psutil.Process(root_pid)
        return [root, *root.children(recursive=True)]
    except psutil.Error:
        return []


def _run_cycle(
    *,
    stream_count: int,
    cycle: int,
    source: Path,
    executable: Path,
    output_root: Path,
    levels: str,
    threads: int,
    prefetch_policy: str,
    prefetch_capacity: int | None,
    isolated_cache: bool,
    speech: bool,
    narrator_mode: str,
    iterative_axis: str | None,
    timeout_seconds: float,
    disk_queue_sampler: _DiskQueueSampler,
) -> dict[str, Any]:
    run_dir = output_root / f"{stream_count}x" / f"cycle-{cycle:04d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    processes: list[dict[str, Any]] = []
    cycle_started = time.perf_counter()
    for replica in range(stream_count):
        replica_dir = run_dir / f"stream-{replica + 1:02d}"
        replica_dir.mkdir(parents=True, exist_ok=True)
        timeline = replica_dir / "timeline.jsonl"
        log_path = replica_dir / "process.log"
        stream_id = f"fullstack-{stream_count}x-c{cycle:04d}-s{replica + 1:02d}"
        command = [
            str(executable),
            "analyze",
            str(source),
            "--levels",
            levels,
            "--cpu-only",
            "--offline",
            "--threads",
            str(threads),
            "--window-seconds",
            "5",
            "--prefetch-overflow-policy",
            prefetch_policy,
            "--stream-id",
            stream_id,
            "--output",
            str(timeline),
        ]
        if isolated_cache:
            command.extend(["--cache-dir", str(replica_dir / "embedding_cache")])
        if prefetch_capacity is not None:
            command.extend(["--prefetch-capacity", str(prefetch_capacity)])
        if speech:
            command.append("--speech")
        if "L3" in {item.strip() for item in levels.split(",")}:
            command.extend(["--narrator-mode", narrator_mode])
        if iterative_axis:
            command.extend(["--iterative-axis", iterative_axis])
        log_stream = log_path.open("wb")
        try:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=log_stream,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except Exception:
            log_stream.close()
            raise
        processes.append(
            {
                "replica": replica + 1,
                "process": process,
                "log_stream": log_stream,
                "log_path": log_path,
                "timeline_path": timeline,
                "command": command,
                "started": time.perf_counter(),
                "finished": None,
                "return_code": None,
                "timed_out": False,
            }
        )

    rss_samples: list[float] = []
    cpu_percent_samples: list[float] = []
    host_cpu_samples: list[float] = []
    disk_queue_depth_samples: list[float] = []
    cpu_seconds = 0.0
    previous_cpu: dict[tuple[int, float], float] = {}
    previous_sample = time.perf_counter()
    psutil.cpu_percent(interval=None)
    while True:
        now = time.perf_counter()
        live = [entry for entry in processes if entry["process"].poll() is None]
        if not live:
            break
        for entry in live:
            if now - entry["started"] > timeout_seconds:
                entry["timed_out"] = True
                for proc in _process_tree(entry["process"].pid):
                    try:
                        proc.terminate()
                    except psutil.Error:
                        pass
                try:
                    entry["process"].wait(timeout=3)
                except subprocess.TimeoutExpired:
                    entry["process"].kill()
        current_rss = 0
        interval_cpu = 0.0
        seen: set[tuple[int, float]] = set()
        for entry in processes:
            if entry["process"].poll() is not None:
                continue
            for proc in _process_tree(entry["process"].pid):
                try:
                    identity = (proc.pid, proc.create_time())
                    if identity in seen:
                        continue
                    seen.add(identity)
                    with proc.oneshot():
                        current_rss += proc.memory_info().rss
                        cpu = proc.cpu_times()
                    cpu_now = cpu.user + cpu.system
                    cpu_before = previous_cpu.get(identity, cpu_now)
                    interval_cpu += max(0.0, cpu_now - cpu_before)
                    previous_cpu[identity] = cpu_now
                except psutil.Error:
                    continue
        elapsed = max(now - previous_sample, 1e-6)
        previous_sample = now
        cpu_seconds += interval_cpu
        rss_samples.append(current_rss / (1024 * 1024))
        cpu_percent_samples.append(interval_cpu / elapsed * 100)
        host_cpu_samples.append(psutil.cpu_percent(interval=None))
        disk_queue_depth = disk_queue_sampler.sample()
        if disk_queue_depth is not None:
            disk_queue_depth_samples.append(disk_queue_depth)
        for entry in processes:
            if entry["finished"] is None and entry["process"].poll() is not None:
                entry["finished"] = time.perf_counter()
                entry["return_code"] = entry["process"].returncode
        time.sleep(0.1)

    finished_at = time.perf_counter()
    for entry in processes:
        if entry["finished"] is None:
            entry["finished"] = finished_at
            entry["return_code"] = entry["process"].poll()
        entry["log_stream"].close()

    results: list[dict[str, Any]] = []
    for entry in processes:
        result = _parse_timeline(entry)
        result.update(
            {
                "replica": entry["replica"],
                "status": (
                    "timeout"
                    if entry["timed_out"]
                    else "passed"
                    if entry["return_code"] == 0 and result.get("metrics")
                    else "failed"
                ),
                "return_code": entry["return_code"],
                "wall_seconds": round(entry["finished"] - entry["started"], 3),
                "log": str(entry["log_path"].relative_to(ROOT)),
                "timeline": str(entry["timeline_path"].relative_to(ROOT)),
                "command": entry["command"],
            }
        )
        source_duration_ms = result.get("source_duration_ms")
        result["rtf"] = (
            round(float(result["wall_seconds"]) / (float(source_duration_ms) / 1000), 4)
            if isinstance(source_duration_ms, (int, float)) and source_duration_ms > 0
            else None
        )
        results.append(result)
    duration = max(finished_at - cycle_started, 1e-6)
    return {
        "cycle": cycle,
        "stream_count": stream_count,
        "status": "passed" if all(result["status"] == "passed" for result in results) else "failed",
        "wall_seconds": round(duration, 3),
        "process_tree": {
            "sample_interval_ms": 100,
            "peak_aggregate_rss_mb": round(max(rss_samples, default=0.0), 3),
            "mean_aggregate_rss_mb": round(statistics.fmean(rss_samples), 3)
            if rss_samples
            else 0.0,
            "mean_cpu_percent_one_core": round(statistics.fmean(cpu_percent_samples), 3)
            if cpu_percent_samples
            else 0.0,
            "peak_cpu_percent_one_core": round(max(cpu_percent_samples), 3)
            if cpu_percent_samples
            else 0.0,
            "cpu_seconds": round(cpu_seconds, 3),
            "mean_host_cpu_percent": round(statistics.fmean(host_cpu_samples), 3)
            if host_cpu_samples
            else 0.0,
            "peak_host_cpu_percent": round(max(host_cpu_samples), 3) if host_cpu_samples else 0.0,
            "disk_queue_depth_samples": disk_queue_depth_samples,
        },
        "streams": results,
    }


def _parse_timeline(entry: dict[str, Any]) -> dict[str, Any]:
    timeline = entry["timeline_path"]
    records: list[dict[str, Any]] = []
    if timeline.exists():
        for line in timeline.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    counts = Counter(str(record.get("record_type", "unknown")) for record in records)
    narration_records = [record for record in records if record.get("record_type") == "caption"]
    narration_latency_samples = [
        float(record["latency_ms"])
        for record in narration_records
        if isinstance(record.get("latency_ms"), (int, float))
    ]
    narration_backend_counts = Counter(
        str(record.get("backend", "unknown")) for record in narration_records
    )
    narration_status_counts = Counter(
        str(record.get("status", "unknown")) for record in narration_records
    )
    narration_warning_counts = Counter(
        str(warning)
        for record in narration_records
        for warning in record.get("warnings", [])
        if isinstance(warning, str)
    )
    narration_unsupported_claim_count = sum(
        len(record.get("new_unsupported_claims", []))
        for record in narration_records
        if isinstance(record.get("new_unsupported_claims", []), list)
    )
    hypothesis_records = [
        record for record in records if record.get("record_type") == "hypothesis_iteration"
    ]
    hypothesis_proposal_latency_samples = [
        float(record["proposal_latency_ms"])
        for record in hypothesis_records
        if record.get("status") != "reused"
        if isinstance(record.get("proposal_latency_ms"), (int, float))
        and float(record["proposal_latency_ms"]) > 0
    ]
    hypothesis_embedding_latency_samples = [
        float(record["embedding_latency_ms"])
        for record in hypothesis_records
        if record.get("status") != "reused"
        if isinstance(record.get("embedding_latency_ms"), (int, float))
        and float(record["embedding_latency_ms"]) > 0
    ]
    generated_candidate_ids = sorted(
        {
            str(candidate_id)
            for record in hypothesis_records
            for candidate_id in record.get("generated_candidate_ids", [])
            if isinstance(candidate_id, str)
        }
    )
    hypothesis_status_counts = Counter(
        str(record.get("status", "unknown")) for record in hypothesis_records
    )
    hypothesis_error_counts = Counter(
        str(record.get("error", "")).split(":", 1)[0]
        for record in hypothesis_records
        if isinstance(record.get("error"), str) and record.get("error")
    )
    dynamic_selected_count = sum(
        str(record.get("selected_candidate_id", "")).startswith("iterative_")
        for record in hypothesis_records
    )
    metrics = next(
        (record for record in reversed(records) if record.get("record_type") == "metrics"), None
    )
    analysis = next((record for record in records if record.get("record_type") == "analysis"), {})
    active_levels = set(analysis.get("active_levels", []))
    watermark_lags = {f"L{level}": [] for level in (1, 2, 3)}
    embedding_latencies = {"audio": [], "image": []}
    for record in records:
        if record.get("record_type") == "watermark":
            watermarks = record.get("watermarks", {})
            lag = watermarks.get("lag_ms", {}) if isinstance(watermarks, dict) else {}
            if isinstance(lag, dict):
                for level in watermark_lags:
                    value = lag.get(level)
                    if level in active_levels and isinstance(value, (int, float)):
                        watermark_lags[level].append(float(value))
        elif record.get("record_type") == "embedding":
            modality = str(record.get("modality", ""))
            target = "image" if modality in {"video", "image"} else modality
            latency = record.get("latency_ms")
            if target in embedding_latencies and isinstance(latency, (int, float)):
                embedding_latencies[target].append(float(latency))
    if metrics is None:
        return {"metrics": None, "record_counts": dict(counts), "source_duration_ms": None}

    final = metrics.get("final_watermarks", {})
    issues = final.get("issues", []) if isinstance(final, dict) else []
    dropped_coverage = sum(
        1
        for issue in issues
        if isinstance(issue, dict) and issue.get("status") in {"dropped", "failed"}
    )
    duration_ms = next(
        (
            record.get("source_duration_ms")
            for record in records
            if record.get("record_type") == "analysis"
        ),
        None,
    )
    elapsed = float(metrics.get("end_to_end_elapsed", 0.0))
    return {
        "metrics": metrics,
        "source_duration_ms": duration_ms,
        "analyzer_elapsed_seconds": elapsed,
        "record_counts": dict(counts),
        "embedding_latency_ms": {
            modality: _summary(values, unit="ms")
            for modality, values in embedding_latencies.items()
        },
        "watermark_lag_ms": {
            level: _summary(values, unit="ms") for level, values in watermark_lags.items()
        },
        "watermark_lag_samples_ms": watermark_lags,
        "dropped_or_failed_coverage_count": dropped_coverage,
        "ingest_dropped_count": int(metrics.get("media_ingest", {}).get("dropped_count", 0)),
        "prefetch_dropped_count": sum(
            int(item.get("dropped_count", 0)) for item in metrics.get("prefetch", {}).values()
        ),
        "scheduler_pressure_rejected_count": int(
            metrics.get("semantic_scheduler", {}).get("pressure_rejected_count", 0)
        ),
        "final_watermarks": final,
        "narration_latency_ms_samples": narration_latency_samples,
        "narration_backend_counts": dict(narration_backend_counts),
        "narration_status_counts": dict(narration_status_counts),
        "narration_warning_counts": dict(narration_warning_counts),
        "narration_unsupported_claim_count": narration_unsupported_claim_count,
        "hypothesis_iteration_count": len(hypothesis_records),
        "hypothesis_status_counts": dict(hypothesis_status_counts),
        "hypothesis_error_counts": dict(hypothesis_error_counts),
        "hypothesis_proposal_latency_ms_samples": hypothesis_proposal_latency_samples,
        "hypothesis_embedding_latency_ms_samples": hypothesis_embedding_latency_samples,
        "hypothesis_generated_candidate_ids": generated_candidate_ids,
        "hypothesis_dynamic_selected_count": dynamic_selected_count,
    }


def _scenario_summary(
    cycles: list[dict[str, Any]], started_at: str, ended_at: str
) -> dict[str, Any]:
    passed_streams = [
        stream for cycle in cycles for stream in cycle["streams"] if stream["status"] == "passed"
    ]
    total_wall = max(
        0.0,
        (datetime.fromisoformat(ended_at) - datetime.fromisoformat(started_at)).total_seconds(),
    )
    total_media_s = sum(
        float(stream["source_duration_ms"] or 0) / 1000 for stream in passed_streams
    )
    all_lags: dict[str, list[float]] = {f"L{level}": [] for level in (1, 2, 3)}
    for stream in passed_streams:
        for level, values in stream["watermark_lag_samples_ms"].items():
            all_lags[level].extend(float(value) for value in values)
    cpu_seconds = sum(float(cycle["process_tree"]["cpu_seconds"]) for cycle in cycles)
    disk_queue_depth_samples: list[float] = []
    for cycle in cycles:
        process_tree = cycle["process_tree"]
        cycle_samples = process_tree.pop("disk_queue_depth_samples", [])
        process_tree["disk_queue_depth"] = _summary(cycle_samples, unit="items")
        disk_queue_depth_samples.extend(cycle_samples)
    peak_rss = max(
        (float(cycle["process_tree"]["peak_aggregate_rss_mb"]) for cycle in cycles), default=0.0
    )
    narration_metrics = [
        stream["metrics"].get("narration_token_throughput", {})
        for stream in passed_streams
        if isinstance(stream.get("metrics"), dict)
    ]
    token_counts = [
        int(item["generated_tokens"])
        for item in narration_metrics
        if isinstance(item.get("generated_tokens"), int)
    ]
    generation_durations_ms = [
        float(item["generation_ms"])
        for item in narration_metrics
        if isinstance(item.get("generation_ms"), (int, float))
    ]
    generated_tokens = sum(token_counts) if token_counts else None
    generation_ms = sum(generation_durations_ms) if generation_durations_ms else None
    measured_generations = sum(
        int(item.get("measured_generations", 0)) for item in narration_metrics
    )
    throughput_weights = [
        (float(item["tokens_per_second"]), int(item.get("measured_generations", 0)))
        for item in narration_metrics
        if isinstance(item.get("tokens_per_second"), (int, float))
        and int(item.get("measured_generations", 0)) > 0
    ]
    tokens_per_second = (
        round(
            sum(rate * count for rate, count in throughput_weights)
            / sum(count for _, count in throughput_weights),
            3,
        )
        if throughput_weights
        else round(generated_tokens / (generation_ms / 1000), 3)
        if generated_tokens is not None and generation_ms is not None and generation_ms > 0
        else None
    )
    caption_count = sum(int(item.get("caption_count", 0)) for item in narration_metrics)
    fallback_count = sum(int(item.get("fallback_count", 0)) for item in narration_metrics)
    narration_latency_samples = [
        float(value)
        for stream in passed_streams
        for value in stream.get("narration_latency_ms_samples", [])
    ]
    narration_backend_counts: Counter[str] = Counter()
    narration_status_counts: Counter[str] = Counter()
    narration_warning_counts: Counter[str] = Counter()
    hypothesis_status_counts: Counter[str] = Counter()
    hypothesis_error_counts: Counter[str] = Counter()
    for stream in passed_streams:
        narration_backend_counts.update(stream.get("narration_backend_counts", {}))
        narration_status_counts.update(stream.get("narration_status_counts", {}))
        narration_warning_counts.update(stream.get("narration_warning_counts", {}))
        hypothesis_status_counts.update(stream.get("hypothesis_status_counts", {}))
        hypothesis_error_counts.update(stream.get("hypothesis_error_counts", {}))
    hypothesis_proposal_latency_samples = [
        float(value)
        for stream in passed_streams
        for value in stream.get("hypothesis_proposal_latency_ms_samples", [])
    ]
    hypothesis_embedding_latency_samples = [
        float(value)
        for stream in passed_streams
        for value in stream.get("hypothesis_embedding_latency_ms_samples", [])
    ]
    hypothesis_generated_candidate_ids = sorted(
        {
            str(candidate_id)
            for stream in passed_streams
            for candidate_id in stream.get("hypothesis_generated_candidate_ids", [])
        }
    )
    cores = psutil.cpu_count(logical=True) or 1
    run_rtf = [float(stream["rtf"]) for stream in passed_streams if stream.get("rtf") is not None]
    return {
        "status": "passed"
        if passed_streams and all(cycle["status"] == "passed" for cycle in cycles)
        else "failed",
        "started_at_utc": started_at,
        "ended_at_utc": ended_at,
        "cycle_count": len(cycles),
        "stream_count": cycles[0]["stream_count"] if cycles else 0,
        "completed_stream_cycles": len(passed_streams),
        "wall_seconds": round(total_wall, 3),
        "processed_media_seconds": round(total_media_s, 3),
        "aggregate_rtf": round(total_wall / total_media_s, 4) if total_media_s else None,
        "per_stream_rtf": _summary(run_rtf, unit="rtf"),
        "cpu_core_equivalents_mean": round(cpu_seconds / total_wall, 3) if total_wall else 0.0,
        "cpu_capacity_percent_mean": round(cpu_seconds / (total_wall * cores) * 100, 3)
        if total_wall
        else 0.0,
        "peak_aggregate_process_tree_rss_mb": round(peak_rss, 3),
        "disk_queue_depth": _summary(disk_queue_depth_samples, unit="items"),
        "narration_token_throughput": {
            "generated_tokens": generated_tokens,
            "generation_seconds": round(generation_ms / 1000, 3)
            if generation_ms is not None
            else None,
            "tokens_per_second": tokens_per_second,
            "measured_generations": measured_generations,
            "caption_count": caption_count,
            "fallback_count": fallback_count,
        },
        "narration_latency_ms": _summary(narration_latency_samples, unit="ms"),
        "narration_backend_counts": dict(narration_backend_counts),
        "narration_status_counts": dict(narration_status_counts),
        "narration_warning_counts": dict(narration_warning_counts),
        "narration_unsupported_claim_count": sum(
            int(stream.get("narration_unsupported_claim_count", 0))
            for stream in passed_streams
        ),
        "hypothesis_iteration_count": sum(
            int(stream.get("hypothesis_iteration_count", 0)) for stream in passed_streams
        ),
        "hypothesis_status_counts": dict(hypothesis_status_counts),
        "hypothesis_error_counts": dict(hypothesis_error_counts),
        "hypothesis_generated_candidate_ids": hypothesis_generated_candidate_ids,
        "hypothesis_dynamic_selected_count": sum(
            int(stream.get("hypothesis_dynamic_selected_count", 0)) for stream in passed_streams
        ),
        "hypothesis_proposal_latency_ms": _summary(
            hypothesis_proposal_latency_samples, unit="ms"
        ),
        "hypothesis_embedding_latency_ms": _summary(
            hypothesis_embedding_latency_samples, unit="ms"
        ),
        "total_dropped_or_failed_coverage": sum(
            int(stream.get("dropped_or_failed_coverage_count", 0)) for stream in passed_streams
        ),
        "total_ingest_dropped_count": sum(
            int(stream.get("ingest_dropped_count", 0)) for stream in passed_streams
        ),
        "total_prefetch_dropped_count": sum(
            int(stream.get("prefetch_dropped_count", 0)) for stream in passed_streams
        ),
        "total_scheduler_pressure_rejected_count": sum(
            int(stream.get("scheduler_pressure_rejected_count", 0)) for stream in passed_streams
        ),
        "lag_by_level_ms": {
            level: _summary(values, unit="ms") for level, values in all_lags.items()
        },
        "cycles": cycles,
    }


def _machine_info() -> dict[str, Any]:
    try:
        import cpuinfo

        cpu_brand = cpuinfo.get_cpu_info().get("brand_raw", platform.processor())
    except ImportError:
        cpu_brand = platform.processor()
    memory = psutil.virtual_memory()
    return {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "cpu": cpu_brand,
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "ram_total_bytes": memory.total,
        "ram_available_at_start_bytes": memory.available,
    }


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    cache_label = (
        "isolated per stream/cycle"
        if report["configuration"]["isolated_cache_per_stream"]
        else "shared default cache"
    )
    lines = [
        "# SHSD full-stack concurrent A/V benchmark",
        "",
        f"Generated: `{report['created_at_utc']}`",
        "",
        "## Machine and workload",
        "",
        f"- CPU: {report['machine']['cpu']}",
        f"- OS / Python: {report['machine']['os']} / {report['machine']['python']}",
        f"- Cores: {report['machine']['physical_cores']} physical, "
        f"{report['machine']['logical_cores']} logical",
        f"- Input: `{report['configuration']['source']}` "
        f"({report['configuration']['source_duration_ms']} ms)",
        f"- Levels / threads per stream: {report['configuration']['levels']} / "
        f"{report['configuration']['threads']}",
        f"- Prefetch: `{report['configuration']['prefetch_policy']}`; "
        f"capacity: {report['configuration']['prefetch_capacity'] or 'default'}",
        f"- Embedding cache: {cache_label}",
        f"- GigaAM ASR: {'on' if report['configuration']['speech'] else 'off'}; "
        f"L3 narrator: `{report['configuration']['narrator_mode']}`",
        f"- Iterative text hypothesis axis: "
        f"`{report['configuration']['iterative_axis'] or 'off'}`",
        f"- SHSD: `{report['shsd_version']}`; model revisions: "
        f"{report['configuration']['model_revisions']}",
        "",
        (
            "Measurements are local file replay. Aggregate process CPU is reported as core "
            "equivalents and as a share of logical-core capacity. Timeline watermark backlog "
            "is used for L1/L2/L3 lag. Disk queue depth uses the Windows PhysicalDisk PDH counter "
            "when available; token throughput uses llama.cpp generation timings."
        ),
        "",
        "## Scale results",
        "",
        (
            "| Streams | Status | Cycles | Wall s | Processed media s | Aggregate RTF | "
            "Mean CPU cores | Peak RSS MiB | Disk queue p95/max | Tokens/s | "
            "Coverage misses / L2 rejects | "
            "L1 p50/p95 ms | L2 p50/p95 ms | L3 p50/p95 ms |"
        ),
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|",
    ]
    for _, scenario in report["scenarios"].items():
        lag = scenario["lag_by_level_ms"]
        lag_values = [
            f"{lag[level]['p50_ms']}/{lag[level]['p95_ms']}" if lag[level]["sample_count"] else "—"
            for level in ("L1", "L2", "L3")
        ]
        disk_queue = scenario["disk_queue_depth"]
        disk_queue_text = (
            f"{disk_queue['p95_items']}/{disk_queue['max_items']}"
            if disk_queue["sample_count"]
            else "unavailable"
        )
        tokens_per_second = scenario["narration_token_throughput"]["tokens_per_second"]
        lines.append(
            f"| {scenario['stream_count']} | {scenario['status']} | {scenario['cycle_count']} | "
            f"{scenario['wall_seconds']:.1f} | {scenario['processed_media_seconds']:.1f} | "
            f"{scenario['aggregate_rtf'] if scenario['aggregate_rtf'] is not None else '—'} | "
            f"{scenario['cpu_core_equivalents_mean']:.2f} | "
            f"{scenario['peak_aggregate_process_tree_rss_mb']:.0f} | "
            f"{disk_queue_text} | "
            f"{tokens_per_second if tokens_per_second is not None else '—'} | "
            f"{scenario['total_dropped_or_failed_coverage']} / "
            f"{scenario['total_scheduler_pressure_rejected_count']} | "
            + " | ".join(lag_values)
            + " |"
        )
    lines.extend(["", "## Run details", ""])
    for _, scenario in report["scenarios"].items():
        lines.extend([f"### {scenario['stream_count']} concurrent streams", ""])
        lines.append(
            f"CPU capacity mean: {scenario['cpu_capacity_percent_mean']:.1f}%; "
            f"peak aggregate process-tree RSS: "
            f"{scenario['peak_aggregate_process_tree_rss_mb']:.0f} MiB; "
            f"disk queue p95/max: {scenario['disk_queue_depth']['p95_items']}/"
            f"{scenario['disk_queue_depth']['max_items']} over "
            f"{scenario['disk_queue_depth']['sample_count']} samples; "
            f"Qwen generation: "
            f"{tokens_per_second if tokens_per_second is not None else '—'} tokens/s over "
            f"{scenario['narration_token_throughput']['measured_generations']} measurements; "
            f"L3 latency p50/p95: {scenario['narration_latency_ms']['p50_ms']}/"
            f"{scenario['narration_latency_ms']['p95_ms']} ms; "
            f"backends: {scenario['narration_backend_counts']}; "
            f"fallback reasons: {scenario['narration_warning_counts']}; "
            f"unsupported-claim count: {scenario['narration_unsupported_claim_count']}; "
            f"hypothesis iterations: {scenario['hypothesis_iteration_count']}; "
            f"hypothesis errors: {scenario['hypothesis_error_counts']}; "
            f"generated candidates: {scenario['hypothesis_generated_candidate_ids']}; "
            f"dynamic selections: {scenario['hypothesis_dynamic_selected_count']}; "
            f"completed stream cycles: {scenario['completed_stream_cycles']}."
        )
        lines.append("")
        for cycle in scenario["cycles"]:
            for stream in cycle["streams"]:
                metrics = stream.get("metrics") or {}
                final = stream.get("final_watermarks") or {}
                prefetch_drops = sum(
                    int(item.get("dropped_count", 0))
                    for item in metrics.get("prefetch", {}).values()
                )
                lines.append(
                    f"- Cycle {cycle['cycle']}, stream {stream['replica']}: {stream['status']}, "
                    f"{stream['wall_seconds']:.1f}s, RTF {stream.get('rtf')}, "
                    f"C/E/R={final.get('C')}/{final.get('E')}/{final.get('R', {})}, "
                    f"matches {metrics.get('window_match_count', '—')}, "
                    f"prefetch drops {prefetch_drops}, "
                    f"log `{stream['log']}`."
                )
        lines.append("")
    lines.extend(
        [
            "## Scope",
            "",
            (
                "Short `--cycles 1` runs are concurrency smoke measurements, not endurance-soak "
                "completion. Use `--duration-minutes 1`, `5`, `10`, or `30` to keep replaying "
                "the fixture at the selected concurrency for the requested wall time. Each cycle "
                "is a fresh CLI process and incurs process/model startup cost. By default, "
                "embedding caches are shared; `--isolated-cache` creates a separate cache per "
                "stream and cycle to measure cold media inference. Token throughput is the "
                "measured llama.cpp "
                "generation rate; it is unavailable when L3 is off or timing output is absent."
            ),
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument(
        "--shsd-executable", type=Path, default=ROOT / ".venv" / "Scripts" / "shsd.exe"
    )
    parser.add_argument("--streams", type=int, nargs="+", default=[2, 5])
    parser.add_argument("--cycles", type=int, default=None)
    parser.add_argument("--duration-minutes", type=float, default=None)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--levels", default="L0,L1,L2")
    parser.add_argument(
        "--prefetch-policy", choices=("block", "drop_newest", "drop_oldest"), default="block"
    )
    parser.add_argument("--prefetch-capacity", type=int, default=None)
    parser.add_argument(
        "--isolated-cache",
        action="store_true",
        help="give each stream cycle its own embedding cache for cold inference measurements",
    )
    parser.add_argument("--speech", action="store_true", help="enable GigaAM speech processing")
    parser.add_argument(
        "--narrator-mode",
        choices=("qwen", "template"),
        default="qwen",
        help="use Qwen generation or the source-only template baseline for L3",
    )
    parser.add_argument(
        "--iterative-axis", default=None, help="enable one bounded Qwen hypothesis pass"
    )
    parser.add_argument("--timeout-seconds", type=float, default=1800)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument(
        "--json-report", type=Path, default=DEFAULT_REPORT_DIR / "fullstack_av_soak.json"
    )
    parser.add_argument(
        "--markdown-report", type=Path, default=DEFAULT_REPORT_DIR / "fullstack_av_soak.md"
    )
    args = parser.parse_args()
    if args.cycles is None and args.duration_minutes is None:
        args.cycles = 1
    if (args.cycles is not None and args.cycles < 1) or (
        args.duration_minutes is not None and args.duration_minutes <= 0
    ):
        parser.error("cycles and duration-minutes must be positive")
    if args.cycles is not None and args.duration_minutes is not None:
        parser.error("choose either --cycles or --duration-minutes")
    if not args.streams or any(count < 1 for count in args.streams) or args.threads < 1:
        parser.error("stream counts and threads must be positive")
    if args.prefetch_capacity is not None and args.prefetch_capacity < 1:
        parser.error("prefetch-capacity must be positive")
    source = args.source.resolve()
    executable = args.shsd_executable.resolve()
    if not source.is_file():
        parser.error(f"source file not found: {source}")
    if not executable.is_file():
        parser.error(f"SHSD executable not found: {executable}")
    created = datetime.now(UTC)
    machine_at_start = _machine_info()
    shsd_version = subprocess.run(
        [str(executable), "--version"], capture_output=True, text=True, check=True, timeout=30
    ).stdout.strip()
    run_dir = (
        args.run_dir
        or DEFAULT_REPORT_DIR / "fullstack_av_soak_runs" / created.strftime("%Y%m%dT%H%M%SZ")
    ).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    model_lock = json.loads((ROOT / "models.lock.json").read_text(encoding="utf-8"))
    scenarios: dict[str, Any] = {}
    disk_queue_sampler = _DiskQueueSampler()
    for stream_count in args.streams:
        scenario_start = datetime.now(UTC).isoformat()
        started = time.perf_counter()
        cycles: list[dict[str, Any]] = []
        cycle_index = 0
        while True:
            cycle_index += 1
            print(f"starting {stream_count}x A/V cycle {cycle_index}", flush=True)
            cycle = _run_cycle(
                stream_count=stream_count,
                cycle=cycle_index,
                source=source,
                executable=executable,
                output_root=run_dir,
                levels=args.levels,
                threads=args.threads,
                prefetch_policy=args.prefetch_policy,
                prefetch_capacity=args.prefetch_capacity,
                isolated_cache=args.isolated_cache,
                speech=args.speech,
                narrator_mode=args.narrator_mode,
                iterative_axis=args.iterative_axis,
                timeout_seconds=args.timeout_seconds,
                disk_queue_sampler=disk_queue_sampler,
            )
            cycles.append(cycle)
            print(
                f"finished {stream_count}x cycle {cycle_index}: {cycle['status']}, "
                f"{cycle['wall_seconds']:.1f}s, peak RSS "
                f"{cycle['process_tree']['peak_aggregate_rss_mb']:.0f} MiB",
                flush=True,
            )
            if cycle["status"] != "passed":
                break
            if args.cycles is not None and cycle_index >= args.cycles:
                break
            if (
                args.duration_minutes is not None
                and time.perf_counter() - started >= args.duration_minutes * 60
            ):
                break
        ended_at = datetime.now(UTC).isoformat()
        scenarios[str(stream_count)] = _scenario_summary(cycles, scenario_start, ended_at)
    disk_queue_sampler.close()
    report = {
        "schema_version": 2,
        "created_at_utc": created.isoformat(),
        "runtime_target": "cpu",
        "machine": machine_at_start,
        "shsd_version": shsd_version,
        "model_revision": model_lock["models"]["embeddinggemma2"]["revision"],
        "configuration": {
            "source": str(source),
            "source_duration_ms": None,
            "shsd_executable": str(executable),
            "levels": args.levels,
            "threads": args.threads,
            "prefetch_policy": args.prefetch_policy,
            "prefetch_capacity": args.prefetch_capacity,
            "isolated_cache_per_stream": args.isolated_cache,
            "speech": args.speech,
            "narrator_mode": args.narrator_mode,
            "iterative_axis": args.iterative_axis,
            "model_revisions": {
                "embeddinggemma2": model_lock["models"]["embeddinggemma2"]["revision"],
                **(
                    {"qwen3_0_6b": model_lock["models"]["qwen3_0_6b"]["revision"]}
                    if args.narrator_mode == "qwen" and "L3" in args.levels.split(",")
                    else {}
                ),
                **(
                    {"gigaam_v3_e2e_ctc": model_lock["models"]["gigaam_v3_e2e_ctc"]["revision"]}
                    if args.speech
                    else {}
                ),
            },
            "cycles_requested": args.cycles,
            "duration_minutes_requested": args.duration_minutes,
            "run_dir": str(run_dir),
            "disk_queue_depth": {
                "status": "available"
                if disk_queue_sampler.samples and disk_queue_sampler.error is None
                else "partial"
                if disk_queue_sampler.samples
                else "unavailable",
                "counter": disk_queue_sampler.counter_path,
                "counter_type": disk_queue_sampler.counter_type,
                "sample_interval_ms": 100,
                "sample_count": len(disk_queue_sampler.samples),
                "unavailable_reason": disk_queue_sampler.error,
            },
        },
        "scenarios": scenarios,
    }
    try:
        import av

        with av.open(str(source)) as media:
            report["configuration"]["source_duration_ms"] = round(float(media.duration or 0) / 1000)
    except Exception:
        pass
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_markdown(args.markdown_report, report)
    print(f"JSON report saved: {args.json_report.resolve()}")
    print(f"Markdown report saved: {args.markdown_report.resolve()}")
    return 0 if all(value["status"] == "passed" for value in scenarios.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
