"""Build B0 EventGraph records from independently verified F10 review rows."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

try:
    from .validate_f10_review_labels import (
        DEFAULT_LABELS,
        DEFAULT_MANIFEST,
        validate_review_labels,
    )
except ImportError:
    from validate_f10_review_labels import (
        DEFAULT_LABELS,
        DEFAULT_MANIFEST,
        validate_review_labels,
    )

from shsd.memory.graph import GroundedEventGraph, VisualSequenceEvidence
from shsd.memory.models import TimelineClaim, TimelineEvent

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO_REPORT = (
    DEFAULT_ROOT / "benchmarks/reports/bridge_f10/video_action_sequence_xclip_tears120-140.json"
)
DEFAULT_OUTPUT_DIR = DEFAULT_ROOT / "benchmarks/reports/bridge_f10/reviewed_b0"
_AUDIO_TRANSITION_STATES = {"onset", "offset", "changed"}


def _required_text(row: dict[str, str], field: str) -> str:
    value = row.get(field, "").strip()
    if not value:
        raise ValueError(f"verified review row requires {field}")
    return value


def _require_verified(row: dict[str, str], guide_version: str) -> None:
    if row.get("verification_status", "").strip() != "human_verified":
        raise ValueError(f"{row.get('clip_id', 'clip')}: row is not human_verified")
    if row.get("guide_version", "").strip() != guide_version:
        raise ValueError(f"{row.get('clip_id', 'clip')}: guide version mismatch")
    _required_text(row, "reviewer_id")


def visual_sequence_from_payload(value: dict[str, Any]) -> VisualSequenceEvidence:
    """Restore the typed PTS map from a serialized sequence-only graph report."""
    frames = value.get("frames")
    interval = value.get("timeline_interval_ms")
    if (
        not isinstance(frames, list)
        or not frames
        or not isinstance(interval, list)
        or len(interval) != 2
    ):
        raise ValueError("serialized visual sequence is missing interval or frame evidence")
    source_pts_offset_ms = int(value["source_pts_offset_ms"])
    timeline_pts: list[int] = []
    for frame in frames:
        if not isinstance(frame, dict):
            raise ValueError("serialized visual sequence contains an invalid frame record")
        timeline_pts_ms = int(frame["timeline_pts_ms"])
        source_pts_ms = int(frame["source_pts_ms"])
        if source_pts_ms != timeline_pts_ms + source_pts_offset_ms:
            raise ValueError(
                "serialized visual frame source PTS does not match timeline PTS plus offset"
            )
        timeline_pts.append(timeline_pts_ms)
    return VisualSequenceEvidence(
        sequence_id=str(value["sequence_id"]),
        source_id=str(value["source_id"]),
        epoch=int(value["epoch"]),
        timeline_interval_ms=(int(interval[0]), int(interval[1])),
        source_pts_offset_ms=source_pts_offset_ms,
        frame_pts_ms=tuple(timeline_pts),
        frame_token_shapes=tuple(
            tuple(int(size) for size in frame["token_shape"]) for frame in frames
        ),
        model_revision=str(value["model_revision"]),
        preprocess_versions=tuple(str(frame["preprocess_version"]) for frame in frames),
    )


def _annotation_claim(
    *,
    claim_id: str,
    label: str,
    text_ru: str,
    reviewer_id: str,
    guide_version: str,
    clip_id: str,
    evidence_refs: tuple[str, ...],
    visual_subject_ru: str | None = None,
    visual_action_ru: str | None = None,
    visual_object_ru: str | None = None,
    music_layer_type: str | None = None,
    music_layer_state: str | None = None,
) -> TimelineClaim:
    return TimelineClaim(
        claim_id=claim_id,
        label=label,
        text_ru=text_ru,
        decision="accepted",
        raw_cosine=None,
        margin=None,
        evidence_refs=evidence_refs,
        window_ids=(f"human-review:{clip_id}",),
        model_revision="human-review-record",
        sample_count=len(evidence_refs),
        annotation_verification="human_verified",
        annotator_id=reviewer_id,
        guide_version=guide_version,
        visual_subject_ru=visual_subject_ru,
        visual_action_ru=visual_action_ru,
        visual_object_ru=visual_object_ru,
        music_layer_type=music_layer_type,
        music_layer_state=music_layer_state,
    )


def build_reviewed_video_bundle(
    row: dict[str, str],
    clip: dict[str, Any],
    *,
    guide_version: str,
    sequence: VisualSequenceEvidence,
) -> dict[str, Any]:
    """Turn one verified action row into source-grounded B0 claims and Qwen requests."""
    _require_verified(row, guide_version)
    stream_id = str(clip["graph_stream_id"])
    epoch = int(clip["graph_epoch"])
    if sequence.source_id != stream_id or sequence.epoch != epoch:
        raise ValueError("video review clip does not match serialized sequence source or epoch")
    offset = int(clip["source_pts_offset_ms"])
    if sequence.source_pts_offset_ms != offset:
        raise ValueError(
            "video review clip source PTS offset does not match the serialized sequence"
        )
    source_start = int(row["action_start_source_ms"])
    source_end = int(row["action_end_source_ms"])
    source_bounds = tuple(int(value) for value in clip["original_source_interval_ms"])
    if not source_bounds[0] <= source_start < source_end <= source_bounds[1]:
        raise ValueError("verified video action interval is outside the reviewed source clip")
    start_ms, end_ms = source_start - offset, source_end - offset
    evidence_pts = tuple(
        int(value) for value in row["evidence_frame_source_ms"].split(";") if value.strip()
    )
    if len(set(evidence_pts)) < 2 or any(
        not source_bounds[0] <= value < source_bounds[1] for value in evidence_pts
    ):
        raise ValueError("verified video action needs distinct in-clip evidence frame PTS values")
    evidence_refs = tuple(f"visual-frame:{stream_id}:{epoch}:{pts_ms}" for pts_ms in evidence_pts)
    subject = _required_text(row, "subject_ru")
    action = _required_text(row, "action_ru")
    obj = _required_text(row, "object_ru")
    description = _required_text(row, "action_sequence_ru")
    claim = _annotation_claim(
        claim_id=f"{row['clip_id']}:visual-action",
        label="human_verified_visual_action",
        text_ru=description,
        reviewer_id=_required_text(row, "reviewer_id"),
        guide_version=guide_version,
        clip_id=row["clip_id"],
        evidence_refs=evidence_refs,
        visual_subject_ru=subject,
        visual_action_ru=action,
        visual_object_ru=obj,
    )
    event = TimelineEvent(
        stream_id=stream_id,
        epoch=epoch,
        event_id=f"human-review:{row['clip_id']}:visual-action",
        revision=1,
        start_ms=start_ms,
        end_ms=end_ms,
        kind="visual_action",
        level="L2",
        state="committed",
        modality_mask={"audio": False, "video": True, "speech": False},
        claims=(claim,),
    )
    graph = GroundedEventGraph(
        stream_id=stream_id,
        epoch=epoch,
        events=(event,),
        edges=(),
        visual_sequences=(sequence,),
    )
    return {
        "schema_version": 1,
        "record_type": "f10_reviewed_b0_graph",
        "review_mode": "VIDEO_ONLY",
        "source_sha256": clip["source_sha256"],
        "source_interval_ms": [source_start, source_end],
        "event_graph": graph.to_dict(),
        "narration_requests": [asdict(request) for request in graph.narration_requests()],
        "limitations": [
            "The accepted action claim is supplied by a blind human annotation, not X-CLIP.",
            "Visual encoder tokens remain evidence provenance and are not interpreted as actions.",
        ],
    }


def build_reviewed_audio_bundle(
    row: dict[str, str],
    clip: dict[str, Any],
    *,
    guide_version: str,
) -> dict[str, Any]:
    """Turn one verified music-transition row into a source-grounded B0 graph."""
    _require_verified(row, guide_version)
    state = _required_text(row, "music_layer_state")
    if state not in _AUDIO_TRANSITION_STATES:
        raise ValueError("audio review does not confirm a music-layer transition")
    stream_id = str(clip["graph_stream_id"])
    epoch = int(clip["graph_epoch"])
    offset = int(clip["source_pts_offset_ms"])
    source_start = int(row["transition_start_source_ms"])
    source_end = int(row["transition_end_source_ms"])
    source_bounds = tuple(int(value) for value in clip["original_source_interval_ms"])
    if not source_bounds[0] <= source_start < source_end <= source_bounds[1]:
        raise ValueError("verified audio transition interval is outside the reviewed source clip")
    evidence_pts = tuple(
        int(value) for value in row["evidence_audio_source_ms"].split(";") if value.strip()
    )
    if len(set(evidence_pts)) < 2 or any(
        not source_bounds[0] <= value < source_bounds[1] for value in evidence_pts
    ):
        raise ValueError(
            "verified audio transition needs distinct in-clip evidence audio PTS values"
        )
    if not any(value < source_start for value in evidence_pts) or not any(
        value >= source_end for value in evidence_pts
    ):
        raise ValueError("verified audio transition evidence must bracket the transition")
    evidence_refs = tuple(f"audio-review:{stream_id}:{epoch}:{pts_ms}" for pts_ms in evidence_pts)
    reviewer_id = _required_text(row, "reviewer_id")
    layer_type = _required_text(row, "music_layer_type")
    transition = _annotation_claim(
        claim_id=f"{row['clip_id']}:music-transition",
        label="human_verified_music_transition",
        text_ru=_required_text(row, "music_layer_change_ru"),
        reviewer_id=reviewer_id,
        guide_version=guide_version,
        clip_id=row["clip_id"],
        evidence_refs=evidence_refs,
        music_layer_type=layer_type,
        music_layer_state=state,
    )
    scene = _annotation_claim(
        claim_id=f"{row['clip_id']}:audio-scene",
        label="human_verified_audio_scene",
        text_ru=_required_text(row, "audio_scene_ru"),
        reviewer_id=reviewer_id,
        guide_version=guide_version,
        clip_id=row["clip_id"],
        evidence_refs=evidence_refs,
    )
    event = TimelineEvent(
        stream_id=stream_id,
        epoch=epoch,
        event_id=f"human-review:{row['clip_id']}:music-transition",
        revision=1,
        start_ms=source_start - offset,
        end_ms=source_end - offset,
        kind="music_transition",
        level="L2",
        state="committed",
        modality_mask={"audio": True, "video": False, "speech": False},
        claims=(transition, scene),
    )
    graph = GroundedEventGraph(
        stream_id=stream_id,
        epoch=epoch,
        events=(event,),
        edges=(),
    )
    return {
        "schema_version": 1,
        "record_type": "f10_reviewed_b0_graph",
        "review_mode": "AUDIO_ONLY",
        "source_sha256": clip["source_sha256"],
        "source_interval_ms": [source_start, source_end],
        "source_audio_scene": row["audio_scene_ru"],
        "music_layer_type": layer_type,
        "music_layer_state": state,
        "event_graph": graph.to_dict(),
        "narration_requests": [asdict(request) for request in graph.narration_requests()],
        "limitations": [
            "The accepted transition and scene claims are supplied by a blind human annotation.",
            (
                "The audio PTS references identify reviewer evidence points, "
                "not model token alignment."
            ),
        ],
    }


def _load_rows(labels_path: Path) -> dict[str, dict[str, str]]:
    with labels_path.open("r", encoding="utf-8-sig", newline="") as stream:
        return {row["clip_id"].strip(): row for row in csv.DictReader(stream)}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _narration_request_from_payload(value: dict[str, Any]) -> Any:
    from shsd.captions import (
        NarrationASRQuote,
        NarrationClaim,
        NarrationEventRef,
        NarrationRequest,
    )

    return NarrationRequest(
        stream_id=str(value["stream_id"]),
        epoch=int(value["epoch"]),
        event_refs=tuple(NarrationEventRef(**item) for item in value["event_refs"]),
        claims=tuple(
            NarrationClaim(
                **{
                    **item,
                    "evidence_refs": tuple(item.get("evidence_refs", ())),
                }
            )
            for item in value["claims"]
        ),
        asr_quotes=tuple(NarrationASRQuote(**item) for item in value.get("asr_quotes", ())),
        state=value.get("state"),
        delta=value.get("delta"),
    )


def add_qwen_narrations(bundle: dict[str, Any], narrator: Any) -> dict[str, Any]:
    """Run CPU Qwen on the accepted B0 facts and retain coverage/fallback metadata."""
    requests = bundle.get("narration_requests")
    if not isinstance(requests, list) or not requests:
        raise ValueError("reviewed B0 bundle has no narration requests")
    bundle["l3_captions"] = [
        narrator.narrate(_narration_request_from_payload(request)).to_dict() for request in requests
    ]
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--video-sequence-report", type=Path, default=DEFAULT_VIDEO_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--narrate-qwen",
        action="store_true",
        help="also run the pinned local CPU Qwen narrator and save actual L3 captions",
    )
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    args = parser.parse_args()

    errors = validate_review_labels(args.labels, args.manifest)
    if errors:
        print("Cannot build reviewed B0 graphs:")
        for error in errors:
            print(f"- {error}")
        return 1

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    guide_version = str(manifest["review_guide"]["guide_version"])
    rows = _load_rows(args.labels)
    video_report = json.loads(args.video_sequence_report.read_text(encoding="utf-8"))
    video_graph = video_report.get("event_graph")
    sequences = video_graph.get("visual_sequences") if isinstance(video_graph, dict) else None
    if not isinstance(sequences, list) or len(sequences) != 1:
        raise ValueError("video sequence report must contain exactly one PTS-preserving sequence")

    sequence = visual_sequence_from_payload(sequences[0])
    video_bundle = build_reviewed_video_bundle(
        rows["video_01"], manifest["video"], guide_version=guide_version, sequence=sequence
    )
    audio_bundle = build_reviewed_audio_bundle(
        rows["audio_01"], manifest["audio"], guide_version=guide_version
    )
    if args.narrate_qwen:
        from shsd.captions import QwenNarrator

        lock = json.loads((DEFAULT_ROOT / "models.lock.json").read_text(encoding="utf-8"))
        narrator = QwenNarrator(
            lock["models"]["qwen3_0_6b"],
            DEFAULT_ROOT / "models",
            DEFAULT_ROOT,
            threads=args.threads,
            max_tokens=args.max_tokens,
            timeout_seconds=args.timeout_seconds,
        )
        video_bundle = add_qwen_narrations(video_bundle, narrator)
        audio_bundle = add_qwen_narrations(audio_bundle, narrator)
        narration_config = {
            "backend": "qwen_llama_cpp_cpu",
            "model_id": "qwen3_0_6b",
            "model_revision": str(lock["models"]["qwen3_0_6b"]["revision"]),
            "threads": args.threads,
            "max_tokens": args.max_tokens,
            "timeout_seconds": args.timeout_seconds,
        }
        video_bundle["narration_config"] = narration_config
        audio_bundle["narration_config"] = narration_config
    video_path = args.output_dir / "video_only_reviewed_b0.json"
    audio_path = args.output_dir / "audio_only_reviewed_b0.json"
    _write_json(video_path, video_bundle)
    _write_json(audio_path, audio_bundle)
    print(f"Wrote {video_path}")
    print(f"Wrote {audio_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
