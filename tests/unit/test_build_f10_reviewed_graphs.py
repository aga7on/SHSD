from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from scripts.build_f10_reviewed_graphs import (
    build_reviewed_audio_bundle,
    build_reviewed_video_bundle,
    visual_sequence_from_payload,
)
from scripts.validate_f10_review_labels import REQUIRED_COLUMNS


def _video_clip() -> dict[str, Any]:
    return {
        "graph_stream_id": "source-video",
        "graph_epoch": 0,
        "source_pts_offset_ms": 120_000,
        "source_sha256": "a" * 64,
        "original_source_interval_ms": [120_000, 130_000],
    }


def _audio_clip() -> dict[str, Any]:
    return {
        "graph_stream_id": "source-audio",
        "graph_epoch": 0,
        "source_pts_offset_ms": 185_000,
        "source_sha256": "b" * 64,
        "original_source_interval_ms": [185_000, 205_000],
    }


def _video_row() -> dict[str, str]:
    return {
        "clip_id": "video_01",
        "reviewer_id": "reviewer-a",
        "guide_version": "f10-blind-review-v1",
        "verification_status": "human_verified",
        "subject_ru": "мужчина",
        "action_ru": "встаёт",
        "object_ru": "кровать",
        "action_sequence_ru": "Мужчина поднимается с кровати и встаёт рядом.",
        "action_start_source_ms": "121000",
        "action_end_source_ms": "124000",
        "evidence_frame_source_ms": "121000;122000",
    }


def _audio_row() -> dict[str, str]:
    return {
        "clip_id": "audio_01",
        "reviewer_id": "reviewer-b",
        "guide_version": "f10-blind-review-v1",
        "verification_status": "human_verified",
        "audio_scene_ru": "Музыка затихает, затем слышен разговор.",
        "music_layer_type": "music_presence",
        "music_layer_state": "offset",
        "music_layer_change_ru": "Музыка прекращается перед началом разговора.",
        "transition_start_source_ms": "188000",
        "transition_end_source_ms": "190000",
        "evidence_audio_source_ms": "187000;191000",
    }


def _sequence_payload(*, source_id: str = "source-video") -> dict[str, Any]:
    return {
        "sequence_id": "sequence-1",
        "source_id": source_id,
        "epoch": 0,
        "timeline_interval_ms": [0, 5_000],
        "source_pts_offset_ms": 120_000,
        "model_revision": "encoder-revision-1",
        "frames": [
            {
                "timeline_pts_ms": pts_ms,
                "source_pts_ms": pts_ms + 120_000,
                "token_shape": [2, 3],
                "preprocess_version": "image-v1",
            }
            for pts_ms in (0, 1_000, 2_000, 3_000, 4_000)
        ],
    }


def test_verified_video_review_becomes_linked_b0_claim_and_narration_request() -> None:
    sequence = visual_sequence_from_payload(_sequence_payload())

    bundle = build_reviewed_video_bundle(
        _video_row(),
        _video_clip(),
        guide_version="f10-blind-review-v1",
        sequence=sequence,
    )

    graph = bundle["event_graph"]
    claim = graph["nodes"][0]["claims"][0]
    assert graph["nodes"][0]["interval_ms"] == [1_000, 4_000]
    assert claim["decision_state"] == "human_verified"
    assert claim["annotation_verification"] == "human_verified"
    assert claim["visual_subject_ru"] == "мужчина"
    assert claim["visual_action_ru"] == "встаёт"
    assert claim["visual_object_ru"] == "кровать"
    assert claim["evidence_refs"] == [
        "visual-frame:source-video:0:121000",
        "visual-frame:source-video:0:122000",
    ]
    assert bundle["narration_requests"][0]["claims"][0]["text_ru"].startswith("Мужчина")


def test_verified_audio_review_becomes_source_timed_music_transition_claim() -> None:
    bundle = build_reviewed_audio_bundle(
        _audio_row(),
        _audio_clip(),
        guide_version="f10-blind-review-v1",
    )

    graph = bundle["event_graph"]
    event = graph["nodes"][0]
    labels = {claim["label"] for claim in event["claims"]}
    transition = next(
        claim for claim in event["claims"] if claim["label"] == "human_verified_music_transition"
    )
    assert event["interval_ms"] == [3_000, 5_000]
    assert bundle["source_interval_ms"] == [188_000, 190_000]
    assert labels == {"human_verified_music_transition", "human_verified_audio_scene"}
    assert transition["music_layer_type"] == "music_presence"
    assert transition["music_layer_state"] == "offset"
    assert transition["evidence_refs"] == [
        "audio-review:source-audio:0:187000",
        "audio-review:source-audio:0:191000",
    ]
    assert len(bundle["narration_requests"][0]["claims"]) == 2


def test_video_review_rejects_source_or_frame_evidence_mismatch() -> None:
    sequence = visual_sequence_from_payload(_sequence_payload())
    with pytest.raises(ValueError, match="match serialized sequence"):
        build_reviewed_video_bundle(
            _video_row(),
            {**_video_clip(), "graph_stream_id": "another-source"},
            guide_version="f10-blind-review-v1",
            sequence=sequence,
        )

    row = {**_video_row(), "evidence_frame_source_ms": "121500;122000"}
    with pytest.raises(ValueError, match="graph frame evidence"):
        build_reviewed_video_bundle(
            row,
            _video_clip(),
            guide_version="f10-blind-review-v1",
            sequence=sequence,
        )


def test_audio_review_refuses_to_call_presence_a_transition() -> None:
    row = {**_audio_row(), "music_layer_state": "present"}
    with pytest.raises(ValueError, match="does not confirm a music-layer transition"):
        build_reviewed_audio_bundle(
            row,
            _audio_clip(),
            guide_version="f10-blind-review-v1",
        )


def test_direct_builder_cli_loads_validator_and_refuses_blank_labels(tmp_path: Path) -> None:
    guide_version = "f10-blind-review-v1"
    manifest = {
        "review_guide": {"guide_version": guide_version},
        "video": {
            "original_source_interval_ms": [120_000, 130_000],
            "review_frame_pts_ms": [120_000, 121_000],
        },
        "audio": {"original_source_interval_ms": [185_000, 205_000]},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    labels_path = tmp_path / "labels.csv"
    with labels_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        for clip_id in ("video_01", "audio_01"):
            row = dict.fromkeys(REQUIRED_COLUMNS, "")
            row["clip_id"] = clip_id
            writer.writerow(row)

    script_path = Path(__file__).resolve().parents[2] / "scripts/build_f10_reviewed_graphs.py"
    output_dir = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--labels",
            str(labels_path),
            "--manifest",
            str(manifest_path),
            "--video-sequence-report",
            str(tmp_path / "unused.json"),
            "--output-dir",
            str(output_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Cannot build reviewed B0 graphs" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr
    assert not output_dir.exists()
