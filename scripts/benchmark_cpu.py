"""Measure the pinned SHSD CPU path and write JSON plus Markdown reports."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import av
import cpuinfo
import numpy as np
import psutil

from shsd.embeddings.provider import EmbeddingProvider
from shsd.semantic.hypotheses import encode_profile_candidates, load_profiles
from shsd.semantic.matcher import MatchPolicy, SemanticMatcher

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "models.lock.json"
DEFAULT_JSON = ROOT / "benchmarks" / "reports" / "baseline_cpu.json"
DEFAULT_MARKDOWN = ROOT / "benchmarks" / "reports" / "baseline_cpu.md"
SAMPLE_RATE = 16_000

_WORKER_PROVIDER: EmbeddingProvider | None = None


class PeakRssSampler:
    """Sample the parent process and its children while a benchmark stage runs."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.peak_bytes = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def __enter__(self) -> PeakRssSampler:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=1)

    def _sample(self) -> None:
        root = psutil.Process(self.pid)
        while not self._stop.is_set():
            total = 0
            try:
                processes = [root, *root.children(recursive=True)]
                total = sum(process.memory_info().rss for process in processes)
            except psutil.Error:
                pass
            self.peak_bytes = max(self.peak_bytes, total)
            self._stop.wait(0.02)


def _summary(values: list[float], *, unit: str = "ms") -> dict[str, float | int]:
    if not values:
        raise ValueError("cannot summarize an empty sample set")
    return {
        "sample_count": len(values),
        f"mean_{unit}": round(statistics.fmean(values), 3),
        f"p50_{unit}": round(float(np.percentile(values, 50)), 3),
        f"p95_{unit}": round(float(np.percentile(values, 95)), 3),
        f"min_{unit}": round(min(values), 3),
        f"max_{unit}": round(max(values), 3),
    }


def _tone(duration_s: int, phase: float) -> np.ndarray:
    count = SAMPLE_RATE * duration_s
    samples = np.arange(count, dtype=np.float32) / SAMPLE_RATE
    return (0.25 * np.sin(2 * math.pi * 440.0 * samples + phase)).astype(np.float32)


def _load_audio_16k(path: Path) -> np.ndarray:
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=SAMPLE_RATE)
    parts: list[np.ndarray] = []
    with av.open(str(path)) as container:
        for frame in container.decode(audio=0):
            parts.extend(
                np.asarray(converted.to_ndarray(), dtype=np.float32).reshape(-1)
                for converted in resampler.resample(frame)
            )
        parts.extend(
            np.asarray(converted.to_ndarray(), dtype=np.float32).reshape(-1)
            for converted in resampler.resample(None)
        )
    if not parts:
        raise ValueError(f"audio fixture has no samples: {path}")
    return np.concatenate(parts)


def _worker_init(
    model: dict[str, Any], models_dir: str, cache_root: str, threads: int
) -> None:
    global _WORKER_PROVIDER
    _WORKER_PROVIDER = EmbeddingProvider(
        model,
        Path(models_dir),
        cache_dir=Path(cache_root) / f"worker-{os.getpid()}",
        threads=threads,
        enabled_modalities={"audio"},
    )


def _worker_audio(task: tuple[int, float]) -> dict[str, float | bool]:
    if _WORKER_PROVIDER is None:
        raise RuntimeError("embedding worker was not initialized")
    duration_s, phase = task
    started = time.perf_counter()
    record = _WORKER_PROVIDER.encode_audio(
        _tone(duration_s, phase), interval_ms=(0, duration_s * 1000)
    )
    return {"latency_ms": (time.perf_counter() - started) * 1000, "cache_hit": record.cache_hit}


def _benchmark_process_scaling(
    model: dict[str, Any], models_dir: Path, *, workers: list[int], repeats: int
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for worker_count in workers:
        with tempfile.TemporaryDirectory(prefix="shsd-process-bench-") as cache_root:
            tasks = [
                (3, 0.013 * index + worker_count * 0.001)
                for index in range(worker_count * repeats)
            ]
            started = time.perf_counter()
            try:
                with PeakRssSampler(os.getpid()) as memory:
                    with ProcessPoolExecutor(
                        max_workers=worker_count,
                        initializer=_worker_init,
                        initargs=(model, str(models_dir), cache_root, 1),
                    ) as pool:
                        samples = list(pool.map(_worker_audio, tasks, chunksize=1))
                wall_ms = (time.perf_counter() - started) * 1000
                latencies = [float(sample["latency_ms"]) for sample in samples]
                results[str(worker_count)] = {
                    "status": "passed",
                    "worker_count": worker_count,
                    "threads_per_worker": 1,
                    "task_count": len(tasks),
                    "wall_ms": round(wall_ms, 3),
                    "throughput_tasks_per_s": round(len(tasks) / (wall_ms / 1000), 3),
                    "task_latency": _summary(latencies),
                    "peak_process_tree_rss_mb": round(memory.peak_bytes / (1024 * 1024), 3),
                    "cache_misses": sum(not bool(sample["cache_hit"]) for sample in samples),
                }
            except Exception as error:
                results[str(worker_count)] = {
                    "status": "failed",
                    "worker_count": worker_count,
                    "error": f"{type(error).__name__}: {error}",
                }
    return results


def _benchmark_qwen(
    model: dict[str, Any], *, threads: list[int], token_counts: list[int], repeats: int
) -> dict[str, Any]:
    binary_dir = ROOT / "models" / "runtimes" / "llama_cpp" / "b11886" / "bin"
    llama_cli = binary_dir / "llama-cli.exe"
    model_path = ROOT / "models" / "qwen3_0_6b" / model["file"]
    template = ROOT / "configs" / "qwen3_nonthinking.jinja"
    if not llama_cli.is_file() or not model_path.is_file():
        raise FileNotFoundError("Qwen model or llama.cpp runtime is missing; fetch it explicitly")

    prompt = (
        "Событие: измерен непрерывный синтетический тон частотой 440 Гц. "
        "Сформулируй одно короткое предложение только из этого факта."
    )
    results: dict[str, Any] = {}
    version_process = subprocess.run(
        [str(llama_cli), "--version"], capture_output=True, check=True, timeout=30
    )
    runtime = (
        version_process.stdout.decode("utf-8", errors="replace")
        + version_process.stderr.decode("utf-8", errors="replace")
    ).strip()

    for thread_count in threads:
        by_tokens: dict[str, Any] = {}
        for max_tokens in token_counts:
            wall_samples: list[float] = []
            prompt_rates: list[float] = []
            generation_rates: list[float] = []
            memory_peaks: list[float] = []
            for _ in range(repeats):
                command = [
                    str(llama_cli),
                    "--model",
                    str(model_path),
                    "--prompt",
                    prompt,
                    "--chat-template-file",
                    str(template),
                    "--jinja",
                    "--single-turn",
                    "--no-display-prompt",
                    "--simple-io",
                    "--no-warmup",
                    "--perf",
                    "--ignore-eos",
                    "--threads",
                    str(thread_count),
                    "--threads-batch",
                    str(thread_count),
                    "--ctx-size",
                    "1024",
                    "--predict",
                    str(max_tokens),
                    "--temp",
                    "0",
                    "--top-k",
                    "1",
                    "--seed",
                    "7",
                ]
                started = time.perf_counter()
                process = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                )
                with PeakRssSampler(process.pid) as memory:
                    raw_output, _ = process.communicate(timeout=900)
                wall_ms = (time.perf_counter() - started) * 1000
                output = raw_output.decode("utf-8", errors="replace")
                if process.returncode != 0:
                    raise RuntimeError(
                        f"Qwen benchmark exited {process.returncode}: {output[-1000:]}"
                    )
                perf = re.search(
                    r"\[ Prompt:\s*([\d.]+)\s*t/s\s*\|\s*Generation:\s*([\d.]+)\s*t/s\s*\]",
                    output,
                )
                if perf is None:
                    raise RuntimeError("llama.cpp output did not contain prompt/generation timings")
                wall_samples.append(wall_ms)
                prompt_rates.append(float(perf.group(1)))
                generation_rates.append(float(perf.group(2)))
                memory_peaks.append(memory.peak_bytes / (1024 * 1024))
            by_tokens[str(max_tokens)] = {
                "output_tokens_requested": max_tokens,
                "fresh_process_latency": _summary(wall_samples),
                "prompt_processing_tokens_per_s": _summary(
                    prompt_rates, unit="tokens_per_s"
                ),
                "generation_tokens_per_s": _summary(
                    generation_rates, unit="tokens_per_s"
                ),
                "peak_process_rss_mb": round(max(memory_peaks), 3),
            }
        results[str(thread_count)] = by_tokens
    return {"runtime": runtime, "prompt": prompt, "threads": results}


def _benchmark_embeddings(
    model: dict[str, Any],
    models_dir: Path,
    *,
    threads: list[int],
    repeats: int,
    process_counts: list[int],
) -> dict[str, Any]:
    audio_path = ROOT / "tests" / "fixtures" / "media" / "audio_speech_ru.wav"
    video_path = ROOT / "tests" / "fixtures" / "media" / "video_scene_cuts_8s.mp4"
    joint_audio = _load_audio_16k(audio_path)
    joint_interval_ms = (0, round(joint_audio.size * 1000 / SAMPLE_RATE))
    profiles = load_profiles(
        ROOT / "configs" / "hypotheses",
        expected_model_revision=str(model["revision"]),
    )
    music_profile = next(profile for profile in profiles if profile.profile_id == "music")
    music_vectors: dict[str, dict[str, Any]] = {}
    model_load_ms: float

    with tempfile.TemporaryDirectory(prefix="shsd-embedding-bench-") as cache_dir:
        started = time.perf_counter()
        with PeakRssSampler(os.getpid()) as memory:
            provider = EmbeddingProvider(
                model,
                models_dir,
                cache_dir=Path(cache_dir) / "main",
                threads=threads[0],
            )
        model_load_ms = (time.perf_counter() - started) * 1000
        for profile in profiles:
            embedded = encode_profile_candidates(profile, provider)
            if profile.profile_id == "music":
                music_vectors = embedded

        per_thread: dict[str, Any] = {}
        latest_5s_vector: np.ndarray | None = None
        for thread_count in threads:
            provider.set_num_threads(thread_count)
            audio_results: dict[str, Any] = {}
            for duration_s in (3, 5, 10):
                samples: list[float] = []
                for repeat in range(repeats):
                    audio = _tone(duration_s, phase=0.017 * repeat + thread_count * 0.0001)
                    record = provider.encode_audio(
                        audio,
                        interval_ms=(0, duration_s * 1000),
                    )
                    if record.cache_hit:
                        raise RuntimeError("audio benchmark unexpectedly hit the cache")
                    samples.append(record.latency_ms)
                    if duration_s == 5:
                        latest_5s_vector = record.embedding
                audio_results[f"{duration_s}s"] = _summary(samples)

            frame_samples: list[float] = []
            for repeat in range(repeats):
                rng = np.random.default_rng(thread_count * 100 + repeat)
                image = rng.integers(0, 256, size=(360, 640, 3), dtype=np.uint8)
                frame_record = provider.encode_frame(image, pts_ms=repeat * 1000)
                frame_samples.append(frame_record.latency_ms)

            text_samples: list[float] = []
            for repeat in range(repeats):
                text_record = provider.encode_texts(
                    [f"This is benchmark text sample {thread_count}-{repeat}."]
                )[0]
                text_samples.append(text_record.latency_ms)

            video_samples: list[float] = []
            joint_samples: list[float] = []
            video_record = None
            joint_record = None
            with PeakRssSampler(os.getpid()) as mode_memory:
                for _ in range(repeats):
                    video_record = provider.encode_video(
                        video_path, force_recompute=True
                    )
                    video_samples.append(video_record.latency_ms)
                    joint_record = provider.encode_joint(
                        joint_audio,
                        video_path,
                        interval_ms=joint_interval_ms,
                        force_recompute=True,
                    )
                    joint_samples.append(joint_record.latency_ms)
            if latest_5s_vector is None:
                raise RuntimeError("missing 5-second audio embedding for top-k timing")
            if video_record is None or joint_record is None:
                raise RuntimeError("video/joint benchmark produced no samples")
            music_axis = next(
                axis for axis in music_profile.axes if axis.axis_id == "music_presence"
            )
            candidate_vectors = {
                candidate.candidate_id: music_vectors[music_axis.axis_id][
                    candidate.candidate_id
                ].embedding
                for candidate in music_axis.candidates
            }
            matcher = SemanticMatcher()
            policy = MatchPolicy(minimum_similarity=1.0, minimum_margin=2.0, top_k=2)
            top_k_samples: list[float] = []
            claim = None
            for _ in range(repeats):
                stage_start = time.perf_counter()
                claim = matcher.match_axis(
                    music_axis,
                    latest_5s_vector,
                    candidate_vectors,
                    policy=policy,
                    model_revision=str(model["revision"]),
                    evidence_refs=("benchmark:synthetic-5s-tone",),
                )
                top_k_samples.append((time.perf_counter() - stage_start) * 1000)

            per_thread[str(thread_count)] = {
                "audio_only": audio_results,
                "frame_only": _summary(frame_samples),
                "text_only": _summary(text_samples),
                "video_only": {
                    "latency": _summary(video_samples),
                    "embedding_dim": video_record.embedding_dim,
                },
                "joint_audio_video": {
                    "status": "passed",
                    "latency": _summary(joint_samples),
                    "embedding_dim": joint_record.embedding_dim,
                },
                "top_k_match": {
                    "latency": _summary(top_k_samples),
                    "axis_id": music_axis.axis_id,
                    "candidate_ids": [item.candidate_id for item in claim.top_candidates]
                    if claim is not None
                    else [],
                    "raw_cosines": [item.raw_cosine for item in claim.top_candidates]
                    if claim is not None
                    else [],
                },
                "peak_process_rss_mb": round(mode_memory.peak_bytes / (1024 * 1024), 3),
            }

        process_scaling = _benchmark_process_scaling(
            model,
            models_dir,
            workers=process_counts,
            repeats=max(1, repeats),
        )
    return {
        "revision": model["revision"],
        "device": "cpu",
        "dtype": str(provider.encoder.dtype),
        "threads": per_thread,
        "model_load_ms": round(model_load_ms, 3),
        "model_load_peak_process_rss_mb": round(memory.peak_bytes / (1024 * 1024), 3),
        "process_scaling": process_scaling,
        "profile_candidate_count": sum(len(axis.candidates) for axis in music_profile.axes),
        "model_cache_fingerprint": music_profile.candidate_fingerprint(),
    }


def _machine_info() -> dict[str, Any]:
    info = cpuinfo.get_cpu_info()
    flags = sorted(set(info.get("flags", [])))
    memory = psutil.virtual_memory()
    return {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "processor": platform.processor(),
        "cpu_brand": info.get("brand_raw", platform.processor()),
        "architecture": info.get("arch_string_raw", platform.machine()),
        "logical_cores": psutil.cpu_count(logical=True),
        "physical_cores": psutil.cpu_count(logical=False),
        "cpu_flags": flags,
        "available_isa_flags": [
            flag
            for flag in flags
            if flag.startswith(("avx", "sse", "neon", "asimd"))
        ],
        "ram_total_mb": round(memory.total / (1024 * 1024), 3),
    }


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    machine = report["machine"]
    embed = report["embeddinggemma2"]
    lines = [
        "# SHSD CPU baseline",
        "",
        f"Generated: `{report['created_at_utc']}`",
        "",
        "## Machine",
        "",
        f"- CPU: {machine['cpu_brand']}",
        f"- OS / Python: {machine['os']} / {machine['python']}",
        f"- Cores: {machine['physical_cores']} physical, {machine['logical_cores']} logical",
        f"- ISA flags: {', '.join(machine['available_isa_flags']) or 'not reported'}",
        f"- RAM: {machine['ram_total_mb']:.0f} MiB",
        f"- Embedding model load: {embed['model_load_ms']:.1f} ms",
        "- Embedding model load process-tree peak RSS: "
        f"{embed['model_load_peak_process_rss_mb']:.0f} MiB",
        "",
        "## EmbeddingGemma 2",
        "",
        "Latency is CPU wall time per encode call. Repeated inputs use distinct cache keys; "
        "recorded cache hits are flagged.",
        "",
        "| Threads | Audio | Mean ms | p50 ms | p95 ms |",
        "|---:|---:|---:|---:|---:|",
    ]
    for threads, result in embed["threads"].items():
        for duration, stats in result["audio_only"].items():
            lines.append(
                f"| {threads} | {duration} | {stats['mean_ms']:.1f} | "
                f"{stats['p50_ms']:.1f} | {stats['p95_ms']:.1f} |"
            )
    lines.extend(
        [
            "",
            "### Other stages",
            "",
            "| Threads | Text p50/p95 ms | Frame p50/p95 ms | "
            "Video p50/p95 ms | Joint AV p50/p95 ms | Top-k p50/p95 ms |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for threads, result in embed["threads"].items():
        text_stats = result["text_only"]
        frame_stats = result["frame_only"]
        video_stats = result["video_only"]["latency"]
        joint_stats = result["joint_audio_video"]["latency"]
        top_k_stats = result["top_k_match"]["latency"]
        lines.append(
            "| "
            + " | ".join(
                [
                    threads,
                    f"{text_stats['p50_ms']:.1f}/{text_stats['p95_ms']:.1f}",
                    f"{frame_stats['p50_ms']:.1f}/{frame_stats['p95_ms']:.1f}",
                    f"{video_stats['p50_ms']:.1f}/{video_stats['p95_ms']:.1f}",
                    f"{joint_stats['p50_ms']:.1f}/{joint_stats['p95_ms']:.1f}",
                    f"{top_k_stats['p50_ms']:.3f}/{top_k_stats['p95_ms']:.3f}",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Process scaling",
            "",
            "Three-second audio windows run with one CPU thread in each worker.",
            "",
            "| Processes | Tasks | Wall ms | Tasks/s | Task p50 ms | Peak process-tree RSS MiB |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for workers, result in embed["process_scaling"].items():
        if result["status"] == "passed":
            lines.append(
                f"| {workers} | {result['task_count']} | {result['wall_ms']:.1f} | "
                f"{result['throughput_tasks_per_s']:.3f} | "
                f"{result['task_latency']['p50_ms']:.1f} | "
                f"{result['peak_process_tree_rss_mb']:.0f} |"
            )
        else:
            lines.append(f"| {workers} | — | failed | — | — | — |")
            lines.append(f"\nFailure at {workers} processes: `{result['error']}`")
    selected_threads = "4" if "4" in embed["threads"] else next(iter(embed["threads"]))
    selected = embed["threads"][selected_threads]
    compared_stages = {
        "3-second audio embedding": selected["audio_only"]["3s"]["p50_ms"],
        "5-second audio embedding": selected["audio_only"]["5s"]["p50_ms"],
        "10-second audio embedding": selected["audio_only"]["10s"]["p50_ms"],
        "single-frame image embedding": selected["frame_only"]["p50_ms"],
        "8-second video embedding": selected["video_only"]["latency"]["p50_ms"],
        "joint audio/video embedding": selected["joint_audio_video"]["latency"]["p50_ms"],
    }
    slowest_stage = max(compared_stages, key=compared_stages.get)
    lines.extend(
        [
            "",
            "## Measured workload notes",
            "",
            f"At {selected_threads} threads, the slowest measured stage was "
            f"{slowest_stage} ({compared_stages[slowest_stage]:.1f} ms p50).",
            f"The same configuration encoded a 5-second audio window in "
            f"{selected['audio_only']['5s']['p50_ms']:.1f} ms p50 and ran top-k in "
            f"{selected['top_k_match']['latency']['p50_ms']:.3f} ms p50.",
            "These values describe this host and the pinned CPU model; they do not "
            "establish a real-time guarantee.",
        ]
    )
    lines.extend(["", "## Qwen3-0.6B / llama.cpp", ""])
    lines.append(
        "Each sample starts a fresh process and reloads the model; the operating system "
        "file cache may be warm."
    )
    lines.append("")
    lines.append(f"Runtime: `{report['qwen']['runtime'].splitlines()[0]}`")
    lines.append("")
    lines.append(
        "| Threads | Output tokens | Fresh process p50/p95 ms | Prompt tok/s p50/p95 | "
        "Generation tok/s p50/p95 | Peak RSS MiB |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|")
    for threads, outputs in report["qwen"]["threads"].items():
        for tokens, result in outputs.items():
            latency = result["fresh_process_latency"]
            prompt_rate = result["prompt_processing_tokens_per_s"]
            generation_rate = result["generation_tokens_per_s"]
            lines.append(
                f"| {threads} | {tokens} | "
                f"{latency['p50_ms']:.1f}/{latency['p95_ms']:.1f} | "
                f"{prompt_rate['p50_tokens_per_s']:.1f}/"
                f"{prompt_rate['p95_tokens_per_s']:.1f} | "
                f"{generation_rate['p50_tokens_per_s']:.1f}/"
                f"{generation_rate['p95_tokens_per_s']:.1f} | "
                f"{result['peak_process_rss_mb']:.0f} |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", type=Path, default=ROOT / "models")
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-report", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--threads", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if args.repeats < 1 or any(item < 1 for item in [*args.threads, *args.workers]):
        parser.error("repeats, threads, and workers must be positive")
    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    report = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "runtime_target": "cpu",
        "offline_requested": args.offline,
        "machine": _machine_info(),
        "repeats": args.repeats,
        "embeddinggemma2": _benchmark_embeddings(
            lock["models"]["embeddinggemma2"],
            args.models_dir.resolve(),
            threads=args.threads,
            repeats=args.repeats,
            process_counts=args.workers,
        ),
        "qwen": _benchmark_qwen(
            lock["models"]["qwen3_0_6b"],
            threads=args.threads,
            token_counts=[64, 128, 256],
            repeats=args.repeats,
        ),
    }
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_markdown(args.markdown_report, report)
    print(f"JSON report saved to {args.json_report.resolve()}")
    print(f"Markdown report saved to {args.markdown_report.resolve()}")
    return 0


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    raise SystemExit(main())
