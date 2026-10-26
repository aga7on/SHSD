"""Compare standard/adaptive analyzer cost on generated quiet audio controls."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import time
import wave
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "benchmarks" / "reports" / "adaptive_sampling_silence_ab"
WINDOW_MS = 5_000
SAMPLE_RATE = 16_000


def _write_silence(
    path: Path, duration_seconds: int, *, unique_quiet_windows: bool = False
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples_per_chunk = SAMPLE_RATE * 5
    zero_chunk = b"\0\0" * samples_per_chunk
    rng = np.random.default_rng(41_026)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        window_count = duration_seconds // (WINDOW_MS // 1000)
        for _ in range(window_count):
            if unique_quiet_windows:
                # One-LSB dither makes each window unique to the content cache while
                # staying far below the energy-VAD threshold (-42 dBFS).
                chunk = rng.integers(-1, 2, samples_per_chunk, dtype=np.int16).tobytes()
            else:
                chunk = zero_chunk
            wav.writeframesraw(chunk)


def _run_profile(
    executable: Path,
    source: Path,
    output_path: Path,
    profile: str,
    cache_dir: Path,
    threads: int,
) -> dict[str, Any]:
    command = [
        str(executable),
        "analyze",
        str(source),
        "--cpu-only",
        "--offline",
        "--threads",
        str(threads),
        "--window-seconds",
        "5",
        "--levels",
        "L0,L1",
        "--sampling-profile",
        profile,
        "--output",
        str(output_path),
        "--cache-dir",
        str(cache_dir),
    ]
    started = time.perf_counter()
    log_path = output_path.with_suffix(".log")
    cpu_seconds = 0.0
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        tracked = psutil.Process(process.pid)
        while True:
            try:
                tree = [tracked, *tracked.children(recursive=True)]
                total_cpu = 0.0
                for item in tree:
                    try:
                        cpu = item.cpu_times()
                        total_cpu += cpu.user + cpu.system
                    except psutil.Error:
                        continue
                cpu_seconds = max(cpu_seconds, total_cpu)
            except psutil.Error:
                pass
            if process.poll() is not None:
                break
            time.sleep(0.05)
        process.wait(timeout=30)
        log_file.flush()
    wall_seconds = time.perf_counter() - started
    if process.returncode != 0:
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        raise RuntimeError(
            f"{profile} analyzer failed ({process.returncode}): "
            f"{log_text[-4_000:]}"
        )

    records = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    metrics = next(
        (row for row in reversed(records) if row.get("record_type") == "metrics"),
        None,
    )
    if metrics is None:
        raise RuntimeError(f"{profile} analyzer output has no final metrics record")
    config = next(
        (row for row in records if row.get("record_type") == "analysis"),
        {},
    )
    matches = [
        row
        for row in records
        if row.get("record_type") == "window_match" and row.get("axis_id") == "speech_presence"
    ]
    correct = sum(row.get("candidate_id") == "speech_absent" for row in matches)
    accepted = [row for row in matches if row.get("decision") == "accepted"]
    accepted_false_positives = sum(
        row.get("candidate_id") == "speech_present" for row in accepted
    )
    total_windows = metrics["sampling"]["modalities"]["audio"]["opportunities"]
    selected = metrics["sampling"]["modalities"]["audio"]["selected"]
    skipped = metrics["sampling"]["modalities"]["audio"]["skipped"]
    audio_worker = metrics.get("embedding_worker", {}).get("by_modality", {}).get("audio", {})
    cache_hits = int(audio_worker.get("cache_hits", 0))
    inference_ms = float(audio_worker.get("inference_ms", 0.0))
    source_seconds = total_windows * WINDOW_MS / 1000
    return {
        "profile": profile,
        "returncode": process.returncode,
        "wall_seconds": round(wall_seconds, 4),
        "cpu_seconds": round(cpu_seconds, 4),
        "cpu_core_equivalents": round(cpu_seconds / wall_seconds, 4)
        if wall_seconds
        else None,
        "media_seconds": source_seconds,
        "rtf": round(wall_seconds / source_seconds, 5) if source_seconds else None,
        "audio_windows": total_windows,
        "audio_embeddings_selected": selected,
        "audio_embeddings_skipped": skipped,
        "audio_embedding_cache_hits": cache_hits,
        "audio_embedding_cache_misses": max(0, int(audio_worker.get("completed", 0)) - cache_hits),
        "audio_embedding_inference_ms": round(inference_ms, 3),
        "speech_presence_ranked_accuracy_when_sampled": correct / len(matches)
        if matches
        else None,
        "speech_presence_sampled_matches": len(matches),
        "speech_presence_accepted_claims": len(accepted),
        "speech_presence_accepted_false_positives": accepted_false_positives,
        "stage_timings_ms": metrics["stage_timings_ms"],
        "sampling": metrics["sampling"],
        "coverage": metrics["final_watermarks"],
        "model_revision": config.get("embedding_model_revision"),
        "output_file": str(output_path),
        "log_file": str(log_path),
    }


def _median_profile_runs(profile_runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize repeated runs without discarding the raw per-run evidence."""
    result = dict(profile_runs[-1])
    for field in ("wall_seconds", "cpu_seconds", "cpu_core_equivalents", "rtf"):
        values = [float(run[field]) for run in profile_runs if run.get(field) is not None]
        result[field] = round(median(values), 5) if values else None
    stage_names = {
        name
        for run in profile_runs
        for name in run.get("stage_timings_ms", {})
    }
    result["stage_timings_ms"] = {
        name: round(
            median(float(run["stage_timings_ms"][name]) for run in profile_runs), 3
        )
        for name in sorted(stage_names)
        if all(name in run.get("stage_timings_ms", {}) for run in profile_runs)
    }
    for field in (
        "audio_windows",
        "audio_embeddings_selected",
        "audio_embeddings_skipped",
        "audio_embedding_cache_hits",
        "audio_embedding_cache_misses",
        "speech_presence_sampled_matches",
        "speech_presence_accepted_claims",
        "speech_presence_accepted_false_positives",
    ):
        values = [int(run[field]) for run in profile_runs]
        result[field] = int(median(values))
    result["audio_embedding_inference_ms"] = round(
        median(float(run["audio_embedding_inference_ms"]) for run in profile_runs),
        3,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=int, default=180)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument(
        "--unique-quiet-windows",
        action="store_true",
        help=(
            "use per-window one-LSB dither to measure model work without "
            "identical-content cache hits"
        ),
    )
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()
    if args.duration_seconds < 30 or args.duration_seconds % (WINDOW_MS // 1000):
        parser.error("duration-seconds must be at least 30 and divisible by 5")
    if args.repeats < 1:
        parser.error("repeats must be at least 1")
    if args.threads < 1:
        parser.error("threads must be at least 1")
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    signal_name = "synthetic_quiet_dither" if args.unique_quiet_windows else "synthetic_silence"
    source = report_dir / f"{signal_name}_{args.duration_seconds}s.wav"
    _write_silence(
        source,
        args.duration_seconds,
        unique_quiet_windows=args.unique_quiet_windows,
    )
    executable = ROOT / ".venv" / "Scripts" / "shsd.exe"
    if not executable.is_file():
        parser.error(f"SHSD executable not found: {executable}")
    profiles = ("standard", "adaptive")
    runs: list[dict[str, Any]] = []
    results_by_profile: dict[str, list[dict[str, Any]]] = {
        profile: [] for profile in profiles
    }
    for repeat_index in range(args.repeats):
        order = profiles if repeat_index % 2 == 0 else tuple(reversed(profiles))
        repeat_results = {}
        for profile in order:
            output_path = report_dir / f"{profile}_repeat_{repeat_index + 1:02d}.jsonl"
            cache_dir = report_dir / "embedding_cache" / f"{profile}_repeat_{repeat_index + 1:02d}"
            result = _run_profile(
                executable,
                source,
                output_path,
                profile,
                cache_dir,
                args.threads,
            )
            results_by_profile[profile].append(result)
            repeat_results[profile] = result
        runs.append(
            {
                "repeat": repeat_index + 1,
                "execution_order": list(order),
                "profiles": repeat_results,
            }
        )
    summary_by_profile = {
        profile: _median_profile_runs(profile_runs)
        for profile, profile_runs in results_by_profile.items()
    }
    standard, adaptive = (summary_by_profile[profile] for profile in profiles)
    paired_cpu_savings = [
        1 - run["profiles"]["adaptive"]["cpu_seconds"]
        / max(1e-9, run["profiles"]["standard"]["cpu_seconds"])
        for run in runs
    ]
    paired_wall_savings = [
        1 - run["profiles"]["adaptive"]["wall_seconds"]
        / max(1e-9, run["profiles"]["standard"]["wall_seconds"])
        for run in runs
    ]
    paired_audio_stage_savings = [
        1
        - run["profiles"]["adaptive"]["stage_timings_ms"]["audio_consumer_work"]
        / max(
            1e-9,
            run["profiles"]["standard"]["stage_timings_ms"]["audio_consumer_work"],
        )
        for run in runs
    ]
    paired_inference_savings: list[float | None] = []
    for run in runs:
        standard_inference_ms = run["profiles"]["standard"]["audio_embedding_inference_ms"]
        adaptive_inference_ms = run["profiles"]["adaptive"]["audio_embedding_inference_ms"]
        paired_inference_savings.append(
            1 - adaptive_inference_ms / standard_inference_ms
            if standard_inference_ms > 0
            else None
        )
    measured_inference_savings = [
        value for value in paired_inference_savings if value is not None
    ]
    report = {
        "schema_version": 2,
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "purpose": "synthetic quiet control; not a natural accuracy evaluation or training data",
        "configuration": {
            "source": str(source),
            "signal_profile": "one_lsb_dither_unique_windows"
            if args.unique_quiet_windows
            else "digital_silence_identical_windows",
            "duration_seconds": args.duration_seconds,
            "repeats": args.repeats,
            "execution_order": "alternates standard-first and adaptive-first",
            "sample_rate": SAMPLE_RATE,
            "window_ms": WINDOW_MS,
            "heartbeat_ms": WINDOW_MS * 3,
            "levels": "L0,L1",
            "threads": args.threads,
            "model_revision": standard["model_revision"],
        },
        "host": {
            "platform": platform.platform(),
            "processor": platform.processor() or "unknown",
            "logical_cpu_count": psutil.cpu_count(logical=True),
            "physical_cpu_count": psutil.cpu_count(logical=False),
        },
        "profiles": summary_by_profile,
        "runs": runs,
        "comparison": {
            "cpu_seconds_saved": round(standard["cpu_seconds"] - adaptive["cpu_seconds"], 4),
            "cpu_seconds_saved_fraction": round(
                1 - adaptive["cpu_seconds"] / standard["cpu_seconds"], 5
            )
            if standard["cpu_seconds"]
            else None,
            "wall_seconds_saved": round(standard["wall_seconds"] - adaptive["wall_seconds"], 4),
            "audio_embedding_reduction": round(
                1
                - adaptive["audio_embeddings_selected"]
                / max(1, standard["audio_embeddings_selected"]),
                5,
            ),
            "audio_consumer_stage_ms_saved_fraction": round(
                1
                - adaptive["stage_timings_ms"]["audio_consumer_work"]
                / max(1, standard["stage_timings_ms"]["audio_consumer_work"]),
                5,
            ),
            "paired_cpu_savings_fraction_by_repeat": [
                round(value, 5) for value in paired_cpu_savings
            ],
            "paired_cpu_savings_fraction_median": round(median(paired_cpu_savings), 5),
            "paired_wall_savings_fraction_by_repeat": [
                round(value, 5) for value in paired_wall_savings
            ],
            "paired_wall_savings_fraction_median": round(median(paired_wall_savings), 5),
            "paired_audio_consumer_stage_savings_fraction_by_repeat": [
                round(value, 5) for value in paired_audio_stage_savings
            ],
            "paired_audio_consumer_stage_savings_fraction_median": round(
                median(paired_audio_stage_savings), 5
            ),
            "paired_embedding_inference_savings_fraction_by_repeat": [
                round(value, 5) if value is not None else None
                for value in paired_inference_savings
            ],
            "paired_embedding_inference_savings_fraction_median": round(
                median(measured_inference_savings), 5
            )
            if measured_inference_savings
            else None,
            "audio_embedding_cache_hit_rate": round(
                sum(
                    run["profiles"][profile]["audio_embedding_cache_hits"]
                    for run in runs
                    for profile in profiles
                )
                / max(
                    1,
                    sum(
                        run["profiles"][profile]["audio_embedding_cache_hits"]
                        + run["profiles"][profile]["audio_embedding_cache_misses"]
                        for run in runs
                        for profile in profiles
                    ),
                ),
                5,
            ),
            "limitations": [
                (
                    "The source is synthetic quiet audio; one-LSB dither is only an "
                    "inference-cache control, not representative natural media."
                ),
                "Natural-window admission is reported separately on 40 exploratory windows; "
                "their source-description labels are not independent listening review.",
                "Repeated local runs still do not establish a general CPU performance guarantee.",
                (
                    "Per-run embedding caches are isolated; cache hits and inference time "
                    "are reported."
                ),
            ],
        },
    }
    json_path = report_dir / "sampling_profiles_ab.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    inference_savings_median = report["comparison"][
        "paired_embedding_inference_savings_fraction_median"
    ]
    inference_savings_text = (
        f"{inference_savings_median:.1%}"
        if inference_savings_median is not None
        else "not measured (no standard-profile inference time)"
    )
    markdown = [
        "# Adaptive sampling performance A/B",
        "",
        f"Synthetic {report['configuration']['signal_profile']} control; "
        f"{args.repeats} paired repeats "
        "with isolated per-run caches and alternating "
        "execution order; performance and heartbeat evidence only.",
        f"Host: `{report['host']['processor']}`; `{report['host']['platform']}`; "
        f"{report['host']['logical_cpu_count']} logical / "
        f"{report['host']['physical_cpu_count']} physical CPUs; {args.threads} inference threads.",
        "",
        "Profile rows show medians across repeats.",
        "",
        "| Profile | Wall s | CPU s | CPU cores | RTF | Audio windows | "
        "Selected | Skipped | Cache hits | Inference ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary_by_profile.values():
        markdown.append(
            f"| {item['profile']} | {item['wall_seconds']:.3f} | {item['cpu_seconds']:.3f} | "
            f"{item['cpu_core_equivalents']:.3f} | {item['rtf']:.5f} | {item['audio_windows']} | "
            f"{item['audio_embeddings_selected']} | {item['audio_embeddings_skipped']} | "
            f"{item['audio_embedding_cache_hits']} | {item['audio_embedding_inference_ms']:.3f} |"
        )
    markdown.extend(
        [
            "",
            f"Paired CPU savings median: "
            f"{report['comparison']['paired_cpu_savings_fraction_median']:.1%} "
            f"(range {min(paired_cpu_savings):.1%} to {max(paired_cpu_savings):.1%}); "
            f"paired wall savings median: "
            f"{report['comparison']['paired_wall_savings_fraction_median']:.1%}; "
            f"audio embedding reduction: "
            f"{report['comparison']['audio_embedding_reduction']:.1%}; "
            f"paired audio-consumer stage savings median: "
            f"{report['comparison']['paired_audio_consumer_stage_savings_fraction_median']:.1%}.",
            f"Paired model inference savings median: {inference_savings_text}; "
            f"combined cache-hit rate: "
            f"{report['comparison']['audio_embedding_cache_hit_rate']:.1%}.",
            f"Speech-presence top-1 accuracy on sampled silence windows: "
            f"{standard['speech_presence_ranked_accuracy_when_sampled']:.1%} standard and "
            f"{adaptive['speech_presence_ranked_accuracy_when_sampled']:.1%} adaptive. ",
            "Accepted claims / accepted false positives: "
            f"{standard['speech_presence_accepted_claims']}/"
            f"{standard['speech_presence_accepted_false_positives']} standard, "
            f"{adaptive['speech_presence_accepted_claims']}/"
            f"{adaptive['speech_presence_accepted_false_positives']} adaptive.",
            "",
            "This synthetic control does not establish recall on natural audio. See "
            "`../adaptive_sampling_natural_delta.md` for the separate 40-window exploratory "
            "admission report; its source-description labels still need "
            "independent listening review.",
            "",
            "## Paired CPU results",
            "",
            "| Repeat | Execution order | Standard CPU s | Adaptive CPU s | CPU saved |",
            "|---:|---|---:|---:|---:|",
        ]
    )
    for run in runs:
        standard_cpu = run["profiles"]["standard"]["cpu_seconds"]
        adaptive_cpu = run["profiles"]["adaptive"]["cpu_seconds"]
        markdown.append(
            f"| {run['repeat']} | {' → '.join(run['execution_order'])} | "
            f"{standard_cpu:.3f} | {adaptive_cpu:.3f} | "
            f"{1 - adaptive_cpu / max(1e-9, standard_cpu):.1%} |"
        )
    markdown.append("")
    (report_dir / "sampling_profiles_ab.md").write_text("\n".join(markdown), encoding="utf-8")
    print(json.dumps(report["comparison"], ensure_ascii=False, sort_keys=True))
    print(f"JSON report saved: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
