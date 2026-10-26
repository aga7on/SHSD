"""Attach a pinned zero-shot X-CLIP action hypothesis to the B0 EventGraph.

This offline diagnostic uses VIDEO frames only. It records an unverified
entity-action-object candidate and never sends it to Qwen narration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import time
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
from shsd.memory import TimelineEvent, VisualActionHypothesis

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO = ROOT / "benchmarks" / "fixtures" / "real_poc" / "tears_of_steel_120_140s.mp4"
DEFAULT_MODEL_DIR = ROOT / "models" / "cache" / "xclip-base-patch32"
DEFAULT_REPORT = (
    ROOT
    / "benchmarks"
    / "reports"
    / "bridge_f10"
    / "video_action_hypothesis_xclip_tears120-140.json"
)
XCLIP_MODEL_ID = "microsoft/xclip-base-patch32"
XCLIP_REVISION = "a2e27a78a2b5d802e894b8a1ef14f3a8ce490963"
XCLIP_LICENSE = "MIT"
SOURCE_PTS_OFFSET_MS = 120_000

_CANDIDATES = (
    {
        "candidate_id": "lying_on_bed",
        "text_en": "A man lies in bed.",
        "entity": "man",
        "action": "lies on",
        "object": "bed",
        "text_ru": "Мужчина лежит на кровати.",
    },
    {
        "candidate_id": "sitting_up_from_bed",
        "text_en": "A man sits up from lying down on a bed.",
        "entity": "man",
        "action": "sits up from",
        "object": "bed",
        "text_ru": "Мужчина приподнимается с кровати.",
    },
    {
        "candidate_id": "rises_from_bed_to_standing",
        "text_en": "An older man rises from the bed to stand beside it.",
        "entity": "older man",
        "action": "rises from bed to standing beside it",
        "object": "bed",
        "text_ru": "Пожилой мужчина поднимается с кровати и встаёт рядом с ней.",
    },
    {
        "candidate_id": "gets_out_of_bed",
        "text_en": "A man gets out of bed.",
        "entity": "man",
        "action": "gets out of",
        "object": "bed",
        "text_ru": "Мужчина встаёт с кровати.",
    },
    {
        "candidate_id": "reaches_toward_candle",
        "text_en": "A man reaches toward a candle beside the bed.",
        "entity": "man",
        "action": "reaches toward",
        "object": "candle",
        "text_ru": "Мужчина тянется к свече рядом с кроватью.",
    },
    {
        "candidate_id": "stands_beside_bed",
        "text_en": "A man stands beside the bed.",
        "entity": "man",
        "action": "stands beside",
        "object": "bed",
        "text_ru": "Мужчина стоит рядом с кроватью.",
    },
    {
        "candidate_id": "walks_away_from_bed",
        "text_en": "A man walks away from the bed.",
        "entity": "man",
        "action": "walks away from",
        "object": "bed",
        "text_ru": "Мужчина отходит от кровати.",
    },
    {
        "candidate_id": "turns_away_from_bed",
        "text_en": "A man turns away from the bed.",
        "entity": "man",
        "action": "turns away from",
        "object": "bed",
        "text_ru": "Мужчина отворачивается от кровати.",
    },
    {
        "candidate_id": "soldier_points_rifle",
        "text_en": "A soldier points a rifle at a man in bed.",
        "entity": "soldier",
        "action": "points a rifle at",
        "object": "man in bed",
        "text_ru": "Солдат целится из винтовки в мужчину на кровати.",
    },
)


def _load_events(path: Path | None, *, stream_id: str, epoch: int) -> list[TimelineEvent]:
    if path is None:
        return []
    events: list[TimelineEvent] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if value.get("record_type") != "event":
            continue
        event = TimelineEvent.from_dict(
            {key: item for key, item in value.items() if key != "record_type"}
        )
        if event.stream_id != stream_id or event.epoch != epoch:
            raise ValueError(f"timeline event on line {line_number} belongs to another source")
        events.append(event)
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--timeline", type=Path)
    parser.add_argument("--stream-id", default="f10-video-only-tears120-140")
    parser.add_argument("--epoch", type=int, default=0)
    parser.add_argument("--start-ms", type=int, default=1_000)
    parser.add_argument("--end-ms", type=int, default=9_000)
    parser.add_argument("--source-pts-offset-ms", type=int, default=SOURCE_PTS_OFFSET_MS)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    if not args.video.is_file():
        parser.error(f"video does not exist: {args.video}")
    if args.timeline is not None and not args.timeline.is_file():
        parser.error(f"timeline does not exist: {args.timeline}")
    if not (args.model_dir / "model.safetensors").is_file():
        parser.error(
            "pinned X-CLIP model files are missing; download the MIT model snapshot at "
            f"revision {XCLIP_REVISION} into {args.model_dir} before running"
        )
    if (
        args.epoch < 0
        or args.start_ms < 0
        or args.end_ms <= args.start_ms
        or args.source_pts_offset_ms < 0
        or args.threads < 1
    ):
        parser.error("invalid epoch, interval, source PTS offset, or thread count")

    config = json.loads((args.model_dir / "config.json").read_text(encoding="utf-8"))
    local_revision = config.get("_commit_hash")
    if local_revision is not None and local_revision != XCLIP_REVISION:
        parser.error(f"X-CLIP revision mismatch: expected {XCLIP_REVISION}, found {local_revision}")

    import torch
    import transformers
    from transformers import XCLIPModel, XCLIPProcessor

    torch.set_num_threads(args.threads)
    processor = XCLIPProcessor.from_pretrained(args.model_dir, local_files_only=True)
    model = XCLIPModel.from_pretrained(args.model_dir, local_files_only=True).eval().to("cpu")
    frames, frame_pts_ms, video_metadata = _load_video_sample(
        args.video,
        interval_ms=(args.start_ms, args.end_ms),
        max_frames=8,
    )
    if len(frames) != 8:
        parser.error(f"X-CLIP requires 8 frames, but the requested interval yielded {len(frames)}")

    texts = [item["text_en"] for item in _CANDIDATES]
    xclip_inputs = processor(
        text=texts,
        videos=[frames],
        return_tensors="pt",
        padding=True,
    )
    started = time.perf_counter()
    with torch.inference_mode():
        outputs = model(**xclip_inputs)
    xclip_latency_ms = round((time.perf_counter() - started) * 1000, 3)
    scores = outputs.logits_per_video[0].float().cpu().tolist()
    ranked_indices = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
    top_index, runner_up_index = ranked_indices[:2]
    top = _CANDIDATES[top_index]
    margin = float(scores[top_index] - scores[runner_up_index])
    source_id = args.stream_id

    lock = json.loads((ROOT / "models.lock.json").read_text(encoding="utf-8"))
    embedding_model = lock["models"]["embeddinggemma2"]
    feature_provider = EmbeddingProvider(
        embedding_model,
        ROOT / "models",
        cache_dir=Path(gettempdir()) / "shsd-xclip-action-graph-cache",
        threads=args.threads,
        enabled_modalities={"image"},
    )
    frame_records = tuple(
        feature_provider.encode_frame_features(np.asarray(frame.convert("RGB")), pts_ms)
        for frame, pts_ms in zip(frames, frame_pts_ms, strict=True)
    )
    feature_batch = AVFeatureBatch.from_records(
        mode="VIDEO",
        source_id=source_id,
        epoch=args.epoch,
        interval_ms=(args.start_ms, args.end_ms),
        frame_records=frame_records,
    )
    evidence_refs = tuple(
        f"visual-frame:{source_id}:{args.epoch}:{pts_ms + args.source_pts_offset_ms}"
        for pts_ms in frame_pts_ms
    )
    hypothesis_digest = hashlib.sha256(
        "\0".join(
            (
                source_id,
                str(args.epoch),
                str(args.start_ms),
                str(args.end_ms),
                XCLIP_MODEL_ID,
                XCLIP_REVISION,
                str(top["candidate_id"]),
            )
        ).encode("utf-8")
    ).hexdigest()[:24]
    hypothesis = VisualActionHypothesis(
        hypothesis_id=hypothesis_digest,
        source_id=source_id,
        epoch=args.epoch,
        timeline_interval_ms=(args.start_ms, args.end_ms),
        source_pts_offset_ms=args.source_pts_offset_ms,
        subject=str(top["entity"]),
        action=str(top["action"]),
        object=str(top["object"]),
        description_en=str(top["text_en"]),
        description_ru=str(top["text_ru"]),
        score=float(scores[top_index]),
        score_kind="xclip_logit",
        margin=margin,
        model_id=XCLIP_MODEL_ID,
        model_revision=XCLIP_REVISION,
        evidence_refs=evidence_refs,
    )
    events = _load_events(args.timeline, stream_id=source_id, epoch=args.epoch)
    graph = _narration_graph(
        events,
        stream_id=source_id,
        epoch=args.epoch,
        visual_feature_batches=(feature_batch,),
        visual_action_hypotheses=(hypothesis,),
        source_pts_offset_ms=args.source_pts_offset_ms,
    )
    logits = torch.tensor(scores, dtype=torch.float32)
    candidate_softmax = torch.softmax(logits, dim=0).tolist()
    ranked = [
        {
            "candidate_id": str(_CANDIDATES[index]["candidate_id"]),
            "text_en": str(_CANDIDATES[index]["text_en"]),
            "raw_logit": float(scores[index]),
            "candidate_set_softmax": float(candidate_softmax[index]),
        }
        for index in ranked_indices
    ]
    report: dict[str, Any] = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "unverified_model_hypothesis",
        "diagnostic_only": True,
        "mode": "VIDEO_ONLY",
        "audio_passed_to_model": False,
        "host": {"os": platform.platform(), "cpu": platform.processor()},
        "model": {
            "id": XCLIP_MODEL_ID,
            "revision": XCLIP_REVISION,
            "license": XCLIP_LICENSE,
            "transformers_version": transformers.__version__,
        },
        "input": {
            "video": str(args.video),
            "timeline": str(args.timeline) if args.timeline is not None else None,
            "stream_id": source_id,
            "epoch": args.epoch,
            "timeline_interval_ms": [args.start_ms, args.end_ms],
            "source_interval_ms": [
                args.start_ms + args.source_pts_offset_ms,
                args.end_ms + args.source_pts_offset_ms,
            ],
            "source_pts_offset_ms": args.source_pts_offset_ms,
            "frame_pts_ms": list(frame_pts_ms),
            "source_frame_pts_ms": [pts_ms + args.source_pts_offset_ms for pts_ms in frame_pts_ms],
            "video_metadata": video_metadata,
        },
        "xclip": {
            "latency_ms": xclip_latency_ms,
            "candidate_set": [dict(item) for item in _CANDIDATES],
            "ranked_scores": ranked,
            "top_two_logit_margin": margin,
            "softmax_is_conditional_to_candidate_set": True,
            "softmax_is_calibrated_probability": False,
        },
        "event_graph": graph.to_dict(),
        "narration_request_count": len(graph.narration_requests()),
        "limitations": [
            "The model output is an unverified candidate, not a human-verified event.",
            "The top-two margin and candidate-set softmax are not calibrated confidence.",
            (
                "The output is an external diagnostic baseline and is not integrated into "
                "the default analyze route."
            ),
            "The candidate is retained in EventGraph but is not sent to Qwen narration.",
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
                "top_candidate": top["candidate_id"],
                "text_en": top["text_en"],
                "text_ru": top["text_ru"],
                "source_interval_ms": report["input"]["source_interval_ms"],
                "source_frame_pts_ms": report["input"]["source_frame_pts_ms"],
                "score_kind": "xclip_logit",
                "score": round(float(scores[top_index]), 4),
                "runner_up": _CANDIDATES[runner_up_index]["candidate_id"],
                "margin": round(margin, 4),
                "graph_action_hypotheses": len(graph.visual_action_hypotheses),
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
