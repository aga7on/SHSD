"""Attach source-timed per-frame encoder features to the B0 EventGraph for review.

This offline probe preserves exact frame PTS and model provenance. It does not
infer visual entities or actions, and it does not send feature vectors to Qwen.
"""

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

from shsd.analyze import _narration_graph
from shsd.bridge.features import AVFeatureBatch
from shsd.embeddings.provider import EmbeddingProvider, _load_video_sample
from shsd.memory.models import TimelineEvent

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO = ROOT / "benchmarks" / "fixtures" / "real_poc" / "tears_of_steel_120_140s.mp4"
DEFAULT_TIMELINE = ROOT / "benchmarks" / "reports" / "bridge_f10" / "video_only_tears120-140.jsonl"
DEFAULT_REPORT = ROOT / "benchmarks" / "reports" / "bridge_f10" / "video_sequence_graph.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--timeline", type=Path, default=DEFAULT_TIMELINE)
    parser.add_argument("--stream-id", default="f10-video-only-tears120-140")
    parser.add_argument("--epoch", type=int, default=0)
    parser.add_argument("--start-ms", type=int, default=0)
    parser.add_argument("--end-ms", type=int, default=8_000)
    parser.add_argument("--source-pts-offset-ms", type=int, default=120_000)
    parser.add_argument("--max-frames", type=int, default=4)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    if not args.video.is_file() or not args.timeline.is_file():
        parser.error("video and timeline input files must exist")
    if (
        args.epoch < 0
        or args.start_ms < 0
        or args.end_ms <= args.start_ms
        or args.source_pts_offset_ms < 0
        or args.max_frames < 2
        or args.threads < 1
    ):
        parser.error("invalid epoch, interval, PTS offset, frame count, or thread count")

    lock = json.loads((ROOT / "models.lock.json").read_text(encoding="utf-8"))
    model = lock["models"]["embeddinggemma2"]
    provider = EmbeddingProvider(
        model,
        ROOT / "models",
        cache_dir=Path(gettempdir()) / "shsd-video-sequence-graph-cache",
        threads=args.threads,
        enabled_modalities={"image"},
    )
    frames, frame_pts_ms, video_metadata = _load_video_sample(
        args.video,
        interval_ms=(args.start_ms, args.end_ms),
        max_frames=args.max_frames,
    )
    frame_records = tuple(
        provider.encode_frame_features(np.asarray(frame.convert("RGB")), pts_ms)
        for frame, pts_ms in zip(frames, frame_pts_ms, strict=True)
    )
    batch = AVFeatureBatch.from_records(
        mode="VIDEO",
        source_id=args.stream_id,
        epoch=args.epoch,
        interval_ms=(args.start_ms, args.end_ms),
        frame_records=frame_records,
    )

    events: list[TimelineEvent] = []
    for line_number, line in enumerate(args.timeline.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("record_type") == "event":
            try:
                events.append(
                    TimelineEvent.from_dict(
                        {key: value for key, value in record.items() if key != "record_type"}
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    f"invalid timeline event on line {line_number}: {error}"
                ) from error

    graph = _narration_graph(
        events,
        stream_id=args.stream_id,
        epoch=args.epoch,
        visual_feature_batches=(batch,),
        source_pts_offset_ms=args.source_pts_offset_ms,
    )
    graph_payload = graph.to_dict()
    graph_payload["narration_request_count"] = len(graph.narration_requests())
    report: dict[str, Any] = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "feature_provenance_only",
        "network_disabled": True,
        "host": {"os": platform.platform(), "cpu": platform.processor()},
        "input": {
            "video": str(args.video),
            "timeline": str(args.timeline),
            "stream_id": args.stream_id,
            "epoch": args.epoch,
            "timeline_interval_ms": [args.start_ms, args.end_ms],
            "source_pts_offset_ms": args.source_pts_offset_ms,
            "video_metadata": video_metadata,
            "feature_batch": batch.metadata(),
            "frame_encode_latency_ms": [record.latency_ms for record in frame_records],
        },
        "event_graph": graph_payload,
        "limitations": [
            "Per-frame token features and source PTS are attached to overlapping event nodes.",
            "This probe does not infer or verify entity, action, or object labels.",
            (
                "Qwen narration requests still contain accepted timeline claims only; "
                "visual token features are not passed to Qwen."
            ),
            (
                "Source PTS offset maps this excerpt to the original film timeline; "
                "it is supplied by fixture metadata."
            ),
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "frame_pts_ms": list(frame_pts_ms),
                "source_pts_ms": [pts + args.source_pts_offset_ms for pts in frame_pts_ms],
                "graph_nodes": len(graph.events),
                "visual_sequences": len(graph.visual_sequences),
                "narration_request_count": len(graph.narration_requests()),
                "report": str(args.report),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
