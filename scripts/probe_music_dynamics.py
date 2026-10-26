"""Measure label-free score movement on the existing music-detail axes."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import av
import numpy as np

from shsd.analyze import _AudioWindowBuilder
from shsd.embeddings.cache import normalize_embedding
from shsd.embeddings.provider import EmbeddingProvider
from shsd.ingest.decoder import CaptureSpan, DecodedFrame
from shsd.semantic.hypotheses import HypothesisAxis, HypothesisCandidate, load_profiles

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "benchmarks" / "fixtures" / "real_poc" / "tears_of_steel_120_210s.mp4"
DEFAULT_OUTPUT = ROOT / "benchmarks" / "reports" / "music_dynamics_probe_20261026"
MINIMUM_SIMILARITY = 0.60
MINIMUM_MARGIN = 0.05


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


def _axes(profile: Any) -> tuple[HypothesisAxis, ...]:
    return tuple(
        axis
        for axis in profile.axes
        if axis.axis_id
        in {
            "music_presence",
            "vocal_presence",
            "percussion_presence",
            "bass_presence",
            "energy",
            "tempo_feel",
            "instrument_family",
        }
    )


def _row_for_axis(
    axis: HypothesisAxis,
    scores: list[tuple[HypothesisCandidate, float]],
    start_ms: int,
    end_ms: int,
    minimum_similarity: float,
    minimum_margin: float,
) -> dict[str, Any]:
    ranked = sorted(scores, key=lambda item: item[1], reverse=True)
    best_candidate, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else -1.0
    margin = best_score - second_score
    if axis.mutually_exclusive:
        accepted = (
            [best_candidate.candidate_id]
            if best_score >= minimum_similarity and margin >= minimum_margin
            else []
        )
        decision = "accepted" if accepted else "uncertain"
    else:
        accepted = [
            candidate.candidate_id
            for candidate, score in ranked
            if score >= minimum_similarity + minimum_margin
        ]
        decision = "accepted" if accepted else "uncertain"
    return {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "axis_id": axis.axis_id,
        "best_candidate": best_candidate.candidate_id,
        "best_cosine": round(best_score, 6),
        "top_two_margin": round(margin, 6),
        "decision": decision,
        "accepted_candidate_ids": accepted,
        "candidate_scores": {
            candidate.candidate_id: round(score, 6) for candidate, score in ranked
        },
    }


def _summarize(
    rows: list[dict[str, Any]], axes: tuple[HypothesisAxis, ...]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_axis: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_axis[row["axis_id"]].append(row)
    summary: dict[str, Any] = {}
    transitions: list[dict[str, Any]] = []
    candidate_ids = {
        axis.axis_id: {candidate.candidate_id for candidate in axis.candidates}
        for axis in axes
    }
    for axis in axes:
        subset = sorted(by_axis[axis.axis_id], key=lambda row: row["start_ms"])
        best_scores = [float(row["best_cosine"]) for row in subset]
        margins = [float(row["top_two_margin"]) for row in subset]
        winners = Counter(str(row["best_candidate"]) for row in subset)
        accepted = Counter(
            candidate_id
            for row in subset
            for candidate_id in row["accepted_candidate_ids"]
        )
        summary[axis.axis_id] = {
            "window_count": len(subset),
            "mutually_exclusive": axis.mutually_exclusive,
            "best_cosine_min_mean_max": (
                [
                    round(float(np.min(best_scores)), 6),
                    round(float(np.mean(best_scores)), 6),
                    round(float(np.max(best_scores)), 6),
                ]
                if best_scores
                else None
            ),
            "top_two_margin_min_mean_max": (
                [
                    round(float(np.min(margins)), 6),
                    round(float(np.mean(margins)), 6),
                    round(float(np.max(margins)), 6),
                ]
                if margins
                else None
            ),
            "decision_counts": dict(Counter(str(row["decision"]) for row in subset)),
            "top_candidate_counts": {
                candidate_id: winners.get(candidate_id, 0)
                for candidate_id in sorted(candidate_ids[axis.axis_id])
            },
            "accepted_candidate_counts": {
                candidate_id: accepted.get(candidate_id, 0)
                for candidate_id in sorted(candidate_ids[axis.axis_id])
            },
        }
        previous: str | None = None
        for row in subset:
            current = str(row["best_candidate"])
            if previous is not None and current != previous:
                transitions.append(
                    {
                        "axis_id": axis.axis_id,
                        "time_ms": row["start_ms"],
                        "from_candidate": previous,
                        "to_candidate": current,
                    }
                )
            previous = current
    return summary, transitions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--window-ms", type=int, default=5_000)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--minimum-similarity", type=float, default=MINIMUM_SIMILARITY)
    parser.add_argument("--minimum-margin", type=float, default=MINIMUM_MARGIN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_file():
        parser.error(f"media source does not exist: {source}")
    if args.window_ms < 250 or args.threads < 1:
        parser.error("window-ms must be at least 250 and threads must be positive")
    if not -1 <= args.minimum_similarity <= 1 or not 0 <= args.minimum_margin <= 2:
        parser.error("invalid similarity or margin threshold")

    model_lock = json.loads((ROOT / "models.lock.json").read_text(encoding="utf-8"))
    model = model_lock["models"]["embeddinggemma2"]
    profile = next(
        item
        for item in load_profiles(
            ROOT / "configs" / "hypotheses",
            expected_model_revision=model["revision"],
        )
        if item.profile_id == "music"
    )
    axes = _axes(profile)
    candidates = [(axis, candidate) for axis in axes for candidate in axis.candidates]
    provider = EmbeddingProvider(
        model,
        ROOT / "models",
        threads=args.threads,
        enabled_modalities={"audio"},
    )
    text_records = provider.encode_texts(
        [candidate.text_en for _, candidate in candidates],
        cache_namespace=f"music-dynamics-probe:{profile.candidate_fingerprint()}",
    )
    vectors = {
        (axis.axis_id, candidate.candidate_id): normalize_embedding(record.embedding)
        for (axis, candidate), record in zip(candidates, text_records, strict=True)
    }
    windows = _audio_windows(source, args.window_ms)
    rows: list[dict[str, Any]] = []
    for start_ms, end_ms, samples in windows:
        audio = normalize_embedding(
            provider.encode_audio(samples, interval_ms=(start_ms, end_ms)).embedding
        )
        for axis in axes:
            scored = [
                (
                    candidate,
                    float(
                        np.dot(
                            audio,
                            vectors[(axis.axis_id, candidate.candidate_id)],
                        )
                    ),
                )
                for candidate in axis.candidates
            ]
            rows.append(
                _row_for_axis(
                    axis,
                    scored,
                    start_ms,
                    end_ms,
                    args.minimum_similarity,
                    args.minimum_margin,
                )
            )

    summary, transitions = _summarize(rows, axes)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "music_dynamics_prompt_scores.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as target:
        fieldnames = [
            "start_ms",
            "end_ms",
            "axis_id",
            "best_candidate",
            "best_cosine",
            "top_two_margin",
            "decision",
            "accepted_candidate_ids",
            "candidate_scores",
        ]
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "accepted_candidate_ids": json.dumps(
                        row["accepted_candidate_ids"], ensure_ascii=False
                    ),
                    "candidate_scores": json.dumps(
                        row["candidate_scores"], ensure_ascii=False, sort_keys=True
                    ),
                }
            )
    report = {
        "schema_version": 1,
        "diagnostic_type": "label_free_music_detail_axis_probe",
        "accuracy_claim": False,
        "similarity_is_probability": False,
        "production_music_gate_bypassed_for_probe": True,
        "source": str(source),
        "model_revision": model["revision"],
        "hypothesis_profile": profile.profile_id,
        "hypothesis_profile_version": profile.profile_version,
        "window_ms": args.window_ms,
        "window_count": len(windows),
        "minimum_similarity": args.minimum_similarity,
        "minimum_margin": args.minimum_margin,
        "axes": {
            axis.axis_id: {
                "mutually_exclusive": axis.mutually_exclusive,
                "candidates": {
                    candidate.candidate_id: {
                        "text_en": candidate.text_en,
                        "text_ru": candidate.text_ru,
                    }
                    for candidate in axis.candidates
                },
            }
            for axis in axes
        },
        "summary": summary,
        "ranked_candidate_transitions": transitions,
        "scores_csv": csv_path.name,
    }
    report_path = output_dir / "music_dynamics_probe.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
