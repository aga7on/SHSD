"""Score the positive-only L1 audio-scene classes on the existing real clip.

The report is label-free. It compares candidate separation, not accuracy, and
keeps the production similarity and margin policy unchanged.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import av
import numpy as np

from shsd.analyze import _AudioWindowBuilder
from shsd.embeddings.cache import normalize_embedding
from shsd.embeddings.provider import EmbeddingProvider
from shsd.ingest.decoder import CaptureSpan, DecodedFrame
from shsd.semantic.hypotheses import load_profiles

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "benchmarks" / "fixtures" / "real_poc" / "tears_of_steel_120_210s.mp4"
DEFAULT_OUTPUT = ROOT / "benchmarks" / "reports" / "music_multiclass_l2_20261026"
BASELINE_SCORES = (
    ROOT
    / "benchmarks"
    / "reports"
    / "music_prompt_probe_20261026"
    / "music_prompt_scores.csv"
)


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


def _baseline_accepts() -> dict[tuple[int, int], str]:
    if not BASELINE_SCORES.is_file():
        return {}
    with BASELINE_SCORES.open(encoding="utf-8-sig", newline="") as source:
        return {
            (int(row["start_ms"]), int(row["end_ms"])): row["decision"]
            for row in csv.DictReader(source)
            if row["prompt_id"] == "baseline"
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--window-ms", type=int, default=5_000)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--minimum-similarity", type=float, default=0.60)
    parser.add_argument("--minimum-margin", type=float, default=0.05)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_file():
        parser.error(f"media source does not exist: {source}")
    if args.window_ms < 250 or args.threads < 1:
        parser.error("window-ms must be at least 250 and threads must be positive")
    if not -1 <= args.minimum_similarity <= 1 or not 0 <= args.minimum_margin <= 2:
        parser.error("invalid similarity or margin threshold")

    lock = json.loads((ROOT / "models.lock.json").read_text(encoding="utf-8"))
    model = lock["models"]["embeddinggemma2"]
    profile = next(
        item
        for item in load_profiles(
            ROOT / "configs" / "hypotheses",
            expected_model_revision=model["revision"],
        )
        if item.profile_id == "music"
    )
    axis = next(item for item in profile.axes if item.axis_id == "music_presence")
    if not axis.mutually_exclusive or any(
        candidate.polarity != "positive" or candidate.opposes for candidate in axis.candidates
    ):
        raise ValueError("L1 audio scene must use positive-only mutually exclusive candidates")

    provider = EmbeddingProvider(
        model,
        ROOT / "models",
        threads=args.threads,
        enabled_modalities={"audio"},
    )
    text_records = provider.encode_texts(
        [candidate.text_en for candidate in axis.candidates],
        cache_namespace=f"music-multiclass-probe:{profile.candidate_fingerprint()}",
    )
    vectors = {
        candidate.candidate_id: normalize_embedding(record.embedding)
        for candidate, record in zip(axis.candidates, text_records, strict=True)
    }
    baseline = _baseline_accepts()
    rows: list[dict[str, Any]] = []
    for start_ms, end_ms, samples in _audio_windows(source, args.window_ms):
        audio = normalize_embedding(
            provider.encode_audio(samples, interval_ms=(start_ms, end_ms)).embedding
        )
        scores = sorted(
            (
                (candidate.candidate_id, float(np.dot(audio, vectors[candidate.candidate_id])))
                for candidate in axis.candidates
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        winner, best = scores[0]
        margin = best - scores[1][1]
        decision = (
            "accepted"
            if best >= args.minimum_similarity and margin >= args.minimum_margin
            else "uncertain"
        )
        rows.append(
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "top_candidate": winner,
                "top_cosine": round(best, 6),
                "runner_up_cosine": round(scores[1][1], 6),
                "top_margin": round(margin, 6),
                "decision": decision,
                "baseline_binary_decision": baseline.get((start_ms, end_ms)),
                **{f"cosine_{candidate_id}": round(score, 6) for candidate_id, score in scores},
            }
        )

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "music_multiclass_scores.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    accepted = [row for row in rows if row["decision"] == "accepted"]
    summary = {
        "schema_version": 1,
        "diagnostic_type": "label_free_positive_only_music_scene_probe",
        "accuracy_claim": False,
        "similarity_is_probability": False,
        "source": str(source),
        "model_revision": model["revision"],
        "profile_version": profile.profile_version,
        "window_ms": args.window_ms,
        "window_count": len(rows),
        "minimum_similarity": args.minimum_similarity,
        "minimum_margin": args.minimum_margin,
        "classes": {
            candidate.candidate_id: {
                "text_en": candidate.text_en,
                "text_ru": candidate.text_ru,
                "polarity": candidate.polarity,
            }
            for candidate in axis.candidates
        },
        "accepted_count": len(accepted),
        "uncertain_count": len(rows) - len(accepted),
        "top_candidate_counts": dict(Counter(str(row["top_candidate"]) for row in rows)),
        "baseline_binary_accepted_count": sum(
            row["baseline_binary_decision"] == "accepted" for row in rows
        ),
        "baseline_binary_comparable_windows": sum(
            row["baseline_binary_decision"] is not None for row in rows
        ),
        "scores_csv": csv_path.name,
    }
    report_path = output_dir / "music_multiclass_probe.json"
    report_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
