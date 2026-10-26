"""Measure adaptive admission recall on the hand-labeled natural audio windows."""

from __future__ import annotations

import argparse
import json
import wave
from pathlib import Path
from typing import Any

import numpy as np

from shsd.detectors import analyze_audio
from shsd.detectors.novelty import compare_audio_windows
from shsd.detectors.types import SignalObservation
from shsd.sampling import AdaptiveSamplingController

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_DIR = ROOT / "benchmarks" / "evaluation" / "iterative_speech_presence_natural"
DEFAULT_JSON = ROOT / "benchmarks" / "reports" / "adaptive_sampling_natural_delta.json"
DEFAULT_MARKDOWN = ROOT / "benchmarks" / "reports" / "adaptive_sampling_natural_delta.md"


def _read_pcm16(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError(f"expected 16-bit PCM WAV: {path}")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, sample_rate


def evaluate(
    eval_dir: Path,
    *,
    window_ms: int,
    heartbeat_windows: int,
    silence_control_windows: int,
) -> dict[str, Any]:
    labels_path = eval_dir / "expected_segments.jsonl"
    rows = [
        json.loads(line)
        for line in labels_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    audio_cache: dict[str, tuple[np.ndarray, int]] = {}
    controllers: dict[str, AdaptiveSamplingController] = {}
    previous_observations: dict[str, list[SignalObservation]] = {}
    selections: list[dict[str, Any]] = []
    for row in rows:
        stream_id = str(row["stream_id"])
        corpus_file = str(row["corpus_file"])
        if corpus_file not in audio_cache:
            audio_cache[corpus_file] = _read_pcm16(eval_dir / "inputs" / corpus_file)
        samples, sample_rate = audio_cache[corpus_file]
        start_ms = int(row["start_ms"])
        end_ms = int(row["end_ms"])
        start_sample = round(start_ms * sample_rate / 1000)
        end_sample = round(end_ms * sample_rate / 1000)
        window = samples[start_sample:end_sample]
        if window.size == 0:
            raise ValueError(f"empty labeled audio window: {row}")
        controller = controllers.get(stream_id)
        if controller is None:
            controller = AdaptiveSamplingController(
                profile="adaptive",
                window_ms=window_ms,
                heartbeat_windows=heartbeat_windows,
            )
            controllers[stream_id] = controller
        observations = analyze_audio(window, sample_rate, start_ms=start_ms)
        previous = previous_observations.get(stream_id)
        signal_changes = (
            compare_audio_windows(previous, observations) if previous is not None else []
        )
        decision = controller.select_audio(
            start_ms,
            observations,
            signal_changes=signal_changes,
        )
        previous_observations[stream_id] = observations
        selections.append(
            {
                "stream_id": stream_id,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "expected_candidate_id": row["expected_candidate_id"],
                "selected": decision.selected,
                "reason": decision.reason,
                "activity_score": decision.activity_score,
            }
        )

    positives = [row for row in selections if row["expected_candidate_id"] == "speech_present"]
    negatives = [row for row in selections if row["expected_candidate_id"] == "speech_absent"]
    selected_positives = sum(row["selected"] for row in positives)
    selected_negatives = sum(row["selected"] for row in negatives)
    selected_total = selected_positives + selected_negatives
    quiet_controller = AdaptiveSamplingController(
        profile="adaptive",
        window_ms=window_ms,
        heartbeat_windows=heartbeat_windows,
    )
    quiet_samples = np.zeros(round(window_ms * 16_000 / 1000), dtype=np.float32)
    quiet_decisions = []
    previous_quiet_observations: list[SignalObservation] | None = None
    for index in range(silence_control_windows):
        start_ms = index * window_ms
        quiet_observations = analyze_audio(quiet_samples, 16_000, start_ms=start_ms)
        quiet_changes: list[SignalObservation] = (
            compare_audio_windows(previous_quiet_observations, quiet_observations)
            if previous_quiet_observations is not None
            else []
        )
        quiet_decisions.append(
            quiet_controller.select_audio(
                start_ms,
                quiet_observations,
                signal_changes=quiet_changes,
            )
        )
        previous_quiet_observations = quiet_observations
    quiet_selected = sum(item.selected for item in quiet_decisions)
    total_opportunities = len(selections) + silence_control_windows
    total_selected = selected_total + quiet_selected
    return {
        "schema_version": 1,
        "profile": "adaptive",
        "window_ms": window_ms,
        "heartbeat_windows": heartbeat_windows,
        "heartbeat_ms": window_ms * heartbeat_windows,
        "evaluation": {
            "name": eval_dir.name,
            "purpose": "manual evaluation only; not training data",
            "window_count": len(selections),
            "source_count": len({row["stream_id"] for row in selections}),
            "positive_windows": len(positives),
            "negative_windows": len(negatives),
            "standard_selected_windows": len(selections),
            "adaptive_selected_windows": selected_total,
            "adaptive_skipped_windows": len(selections) - selected_total,
            "selection_reduction": (
                1.0 - selected_total / len(selections) if selections else None
            ),
            "natural_selection_reduction": (
                1.0 - selected_total / len(selections) if selections else None
            ),
            "positive_admission_recall": (
                selected_positives / len(positives) if positives else None
            ),
            "negative_windows_skipped": len(negatives) - selected_negatives,
            "all_positive_windows_admitted": selected_positives == len(positives),
            "combined_windows_with_synthetic_silence_control": total_opportunities,
            "combined_standard_selected_windows": total_opportunities,
            "combined_adaptive_selected_windows": total_selected,
            "combined_selection_reduction": (
                1.0 - total_selected / total_opportunities if total_opportunities else None
            ),
        },
        "sampling": {
            stream_id: controller.snapshot()
            for stream_id, controller in sorted(controllers.items())
        },
        "synthetic_silence_control": {
            "windows": silence_control_windows,
            "selected": quiet_selected,
            "skipped": silence_control_windows - quiet_selected,
            "decisions": [
                {"selected": item.selected, "reason": item.reason}
                for item in quiet_decisions
            ],
            "sampling": quiet_controller.snapshot(),
            "description": (
                "Generated zero-valued audio; performance control only, not a natural source."
            ),
        },
        "windows": selections,
        "limitations": [
            (
                "The natural set contains a small exploratory collection of five-second speech, "
                "music, and environmental windows."
            ),
            (
                "Admission recall measures whether the sampler passes labeled positive windows; "
                "it does not measure semantic matcher accuracy."
            ),
            (
                "Labels were assigned from source descriptions and have not been "
                "independently reviewed by listening."
            ),
            "This exploratory result is not representative and is not training data.",
            (
                "The synthetic silence control demonstrates heartbeat behavior only and is "
                "excluded from natural-window recall."
            ),
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    result = report["evaluation"]
    lines = [
        "# Adaptive sampling natural-window evaluation",
        "",
        f"- Windows: {result['window_count']} "
        f"({result['positive_windows']} positive, {result['negative_windows']} negative)",
        f"- Standard embeddings selected: "
        f"{result['standard_selected_windows']}/{result['window_count']}",
        f"- Adaptive embeddings selected: "
        f"{result['adaptive_selected_windows']}/{result['window_count']}",
        f"- Adaptive selection reduction: {result['selection_reduction']:.1%}",
        f"- Positive-window admission recall: {result['positive_admission_recall']:.1%}",
        f"- Synthetic silence control: {report['synthetic_silence_control']['selected']}/"
        f"{report['synthetic_silence_control']['windows']} selected",
        f"- Reduction including synthetic silence control: "
        f"{result['combined_selection_reduction']:.1%}",
        f"- Heartbeat: every {report['heartbeat_ms']} ms during low activity",
        f"- All positive windows admitted: {result['all_positive_windows_admitted']}",
        "",
        "This is an exploratory admission test, not semantic accuracy or a representative dataset.",
        "The source-description labels still need independent listening review.",
        (
            "The exact per-window decisions, change scores, source grouping, and limitations "
            "are in the adjacent JSON."
        ),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR)
    parser.add_argument("--window-ms", type=int, default=5_000)
    parser.add_argument("--heartbeat-windows", type=int, default=3)
    parser.add_argument("--silence-control-windows", type=int, default=4)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-report", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    report = evaluate(
        args.eval_dir.resolve(),
        window_ms=args.window_ms,
        heartbeat_windows=args.heartbeat_windows,
        silence_control_windows=args.silence_control_windows,
    )
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.markdown_report.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["evaluation"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
