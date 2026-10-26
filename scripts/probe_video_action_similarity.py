"""Report raw VIDEO/text similarities for action hypotheses without publishing claims."""

from __future__ import annotations

import argparse
import json
import os
import platform
from datetime import UTC, datetime
from pathlib import Path
from tempfile import gettempdir
from typing import Any

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np

from shsd.embeddings.provider import EmbeddingProvider, _load_video_sample

ROOT = Path(__file__).resolve().parents[1]
_CANDIDATES = (
    ("lying_on_bed", "A gray-haired man is lying on a bed."),
    ("sitting_up_from_bed", "A gray-haired man sits up from a bed."),
    ("getting_out_of_bed", "A gray-haired man gets out of bed and stands beside it."),
    ("walking_away_from_bed", "A gray-haired man walks away from a bed across a room."),
    ("reaching_toward_candle", "A gray-haired man reaches toward a candle next to a bed."),
    ("kneeling_with_rifle", "A soldier kneels beside a bed and holds a rifle."),
    ("playing_piano", "A woman plays a piano in a concert hall."),
    ("empty_room", "An empty room with a bed and a candle."),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "video",
        type=Path,
        nargs="?",
        default=ROOT / "benchmarks" / "fixtures" / "real_poc" / "tears_of_steel_120_140s.mp4",
    )
    parser.add_argument("--start-ms", type=int, default=0)
    parser.add_argument("--end-ms", type=int, default=8000)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT
        / "benchmarks"
        / "reports"
        / "bridge_f10"
        / "video_action_similarity_probe.json",
    )
    args = parser.parse_args()
    if not args.video.is_file():
        parser.error(f"video does not exist: {args.video}")
    if args.start_ms < 0 or args.end_ms <= args.start_ms or args.threads < 1:
        parser.error("interval must satisfy 0 <= start_ms < end_ms and threads must be positive")

    lock = json.loads((ROOT / "models.lock.json").read_text(encoding="utf-8"))
    model = lock["models"]["embeddinggemma2"]
    provider = EmbeddingProvider(
        model,
        ROOT / "models",
        cache_dir=Path(gettempdir()) / "shsd-video-action-probe-cache",
        threads=args.threads,
        enabled_modalities={"video"},
    )
    frames, frame_pts_ms, metadata = _load_video_sample(
        args.video,
        interval_ms=(args.start_ms, args.end_ms),
    )
    video_record = provider.encode_video(
        args.video,
        interval_ms=(args.start_ms, args.end_ms),
    )
    texts = [text for _candidate_id, text in _CANDIDATES]
    text_records = provider.encode_texts(texts, cache_namespace="video-action-probe-v1")
    scores = [
        {
            "candidate_id": candidate_id,
            "text_en": text,
            "raw_cosine": float(np.dot(video_record.embedding, text_record.embedding)),
        }
        for (candidate_id, text), text_record in zip(_CANDIDATES, text_records, strict=True)
    ]
    scores.sort(key=lambda item: item["raw_cosine"], reverse=True)
    report: dict[str, Any] = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "diagnostic_only",
        "network_disabled": True,
        "host": {"os": platform.platform(), "cpu": platform.processor()},
        "model_revision": model["revision"],
        "input": {
            "video": str(args.video),
            "interval_ms": [args.start_ms, args.end_ms],
            "sampled_frame_count": len(frames),
            "frame_pts_ms": list(frame_pts_ms),
            "video_metadata": metadata,
            "embedding_window_id": video_record.window_id,
            "embedding_latency_ms": video_record.latency_ms,
            "embedding_cache_hit": video_record.cache_hit,
        },
        "scores": scores,
        "limitations": [
            "Cosine values are similarities, not probabilities or verified labels.",
            "This probe does not emit accepted timeline claims or trainable labels.",
            "Candidate descriptions are diagnostic contrasts, not calibrated thresholds.",
            "The video embedding is pooled; exact temporal evidence remains in the "
            "sampled PTS list.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"status: {report['status']}")
    print(f"json: {args.report}")
    for score in scores:
        print(f"{score['candidate_id']}: cosine={score['raw_cosine']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
