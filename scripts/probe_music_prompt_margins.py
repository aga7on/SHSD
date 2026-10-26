"""Compare music-presence text candidates on real audio without tuning thresholds.

This is a label-free diagnostic. Cosine scores and margins describe candidate
separation only; they are not accuracy or calibrated probabilities.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import av
import numpy as np

from shsd.analyze import _AudioWindowBuilder
from shsd.embeddings.provider import EmbeddingProvider
from shsd.ingest.decoder import CaptureSpan, DecodedFrame

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "benchmarks" / "fixtures" / "real_poc" / "tears_of_steel_120_210s.mp4"

PROMPTS: dict[str, tuple[str, str]] = {
    "baseline": (
        "Music is audible in the audio.",
        "No music is audible in the audio.",
    ),
    "performance_vs_speech_and_noise": (
        "An instrumental or sung musical performance is audible, with melody or rhythm.",
        (
            "Only speech, effects, or environmental sounds are audible; "
            "there is no musical performance."
        ),
    ),
    "tune_beat_vs_words_and_noise": (
        (
            "The audio contains a song or instrumental music, with a tune, beat, "
            "or playing instruments."
        ),
        (
            "The audio contains spoken words or everyday noises, without a tune, "
            "beat, or instrumental playing."
        ),
    ),
    "soundtrack_vs_dialogue_and_effects": (
        "A musical soundtrack is playing under or alongside the other sounds.",
        "There is no soundtrack or music, only dialogue and natural sound effects.",
    ),
}


def _audio_windows(source: Path, window_ms: int) -> list[tuple[int, int, np.ndarray]]:
    builder = _AudioWindowBuilder(window_ms)
    windows: list[tuple[int, int, np.ndarray]] = []
    with av.open(str(source), mode="r") as container:
        if not container.streams.audio:
            raise ValueError("source has no audio stream")
        for frame in container.decode(audio=0):
            windows.extend(
                item
                for item in builder.push(DecodedFrame(frame))
                if not isinstance(item, CaptureSpan)
            )
    windows.extend(builder.finish())
    return windows


def _profile_report(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    for prompt_id in PROMPTS:
        subset = [row for row in rows if row["prompt_id"] == prompt_id]
        positive = [float(row["music_present_cosine"]) for row in subset]
        negative = [float(row["music_absent_cosine"]) for row in subset]
        gaps = [float(row["signed_gap_positive_minus_negative"]) for row in subset]
        absolute = [abs(gap) for gap in gaps]
        accepted = [row for row in subset if row["decision"] == "accepted"]

        def distribution(values: list[float]) -> dict[str, float | None]:
            if not values:
                return {"min": None, "mean": None, "median": None, "max": None}
            return {
                "min": round(float(np.min(values)), 6),
                "mean": round(float(np.mean(values)), 6),
                "median": round(float(np.median(values)), 6),
                "max": round(float(np.max(values)), 6),
            }

        report[prompt_id] = {
            "window_count": len(subset),
            "music_present_cosine": distribution(positive),
            "music_absent_cosine": distribution(negative),
            "mean_signed_gap_positive_minus_negative": (
                round(float(np.mean(gaps)), 6) if gaps else None
            ),
            "mean_absolute_gap": round(float(np.mean(absolute)), 6) if absolute else None,
            "median_absolute_gap": round(float(np.median(absolute)), 6) if absolute else None,
            "min_absolute_gap": round(float(np.min(absolute)), 6) if absolute else None,
            "max_absolute_gap": round(float(np.max(absolute)), 6) if absolute else None,
            "accepted_by_current_policy_count": len(accepted),
            "uncertain_by_current_policy_count": len(subset) - len(accepted),
            "ranked_winner_count": {
                "music_present": sum(row["ranked_winner"] == "music_present" for row in subset),
                "music_absent": sum(row["ranked_winner"] == "music_absent" for row in subset),
            },
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--window-ms", type=int, default=5_000)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--minimum-similarity", type=float, default=0.60)
    parser.add_argument("--minimum-margin", type=float, default=0.05)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "benchmarks" / "reports" / "music_prompt_probe_20261026",
    )
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_file():
        parser.error(f"audio/video source does not exist: {source}")
    if args.window_ms < 250 or args.threads < 1:
        parser.error("window-ms must be at least 250 and threads must be positive")
    if not -1 <= args.minimum_similarity <= 1 or not 0 <= args.minimum_margin <= 2:
        parser.error("invalid similarity or margin threshold")

    model_lock = json.loads((ROOT / "models.lock.json").read_text(encoding="utf-8"))
    model = model_lock["models"]["embeddinggemma2"]
    provider = EmbeddingProvider(
        model,
        ROOT / "models",
        threads=args.threads,
        enabled_modalities={"audio"},
    )
    windows = _audio_windows(source, args.window_ms)
    candidates = [text for pair in PROMPTS.values() for text in pair]
    text_records = provider.encode_texts(candidates, cache_namespace="music-prompt-probe-v1")
    text_vectors = {
        prompt_id: (
            text_records[2 * index].embedding,
            text_records[2 * index + 1].embedding,
        )
        for index, prompt_id in enumerate(PROMPTS)
    }

    rows: list[dict[str, Any]] = []
    for start_ms, end_ms, samples in windows:
        audio = provider.encode_audio(samples, interval_ms=(start_ms, end_ms))
        for prompt_id, (positive_vector, negative_vector) in text_vectors.items():
            positive_score = float(np.dot(audio.embedding, positive_vector))
            negative_score = float(np.dot(audio.embedding, negative_vector))
            signed_gap = positive_score - negative_score
            winner = "music_present" if signed_gap >= 0 else "music_absent"
            best = max(positive_score, negative_score)
            margin = abs(signed_gap)
            accepted = best >= args.minimum_similarity and margin >= args.minimum_margin
            rows.append(
                {
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "prompt_id": prompt_id,
                    "music_present_cosine": round(positive_score, 6),
                    "music_absent_cosine": round(negative_score, 6),
                    "signed_gap_positive_minus_negative": round(signed_gap, 6),
                    "margin": round(margin, 6),
                    "ranked_winner": winner,
                    "decision": "accepted" if accepted else "uncertain",
                    "minimum_similarity": args.minimum_similarity,
                    "minimum_margin": args.minimum_margin,
                }
            )

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "music_prompt_scores.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    report = {
        "schema_version": 1,
        "diagnostic_type": "label_free_prompt_margin_probe",
        "accuracy_claim": False,
        "similarity_is_probability": False,
        "source": str(source),
        "model_revision": model["revision"],
        "window_ms": args.window_ms,
        "window_count": len(windows),
        "minimum_similarity": args.minimum_similarity,
        "minimum_margin": args.minimum_margin,
        "prompt_texts": {
            prompt_id: {"music_present": pair[0], "music_absent": pair[1]}
            for prompt_id, pair in PROMPTS.items()
        },
        "summary": _profile_report(rows),
        "scores_csv": csv_path.name,
    }
    report_path = output_dir / "music_prompt_probe.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
