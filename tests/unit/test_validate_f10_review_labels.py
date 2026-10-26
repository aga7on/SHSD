from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.validate_f10_review_labels import REQUIRED_COLUMNS, validate_review_labels


def _write_manifest(path: Path) -> None:
    manifest = {
        "review_guide": {"guide_version": "f10-blind-review-v1"},
        "video": {
            "original_source_interval_ms": [120_000, 130_000],
            "review_frame_pts_ms": [120_000, 121_000, 122_000, 123_000],
        },
        "audio": {"original_source_interval_ms": [185_000, 205_000]},
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")


def _review_rows() -> list[dict[str, str]]:
    video = dict.fromkeys(REQUIRED_COLUMNS, "")
    video.update(
        {
            "clip_id": "video_01",
            "reviewer_id": "reviewer-a",
            "guide_version": "f10-blind-review-v1",
            "verification_status": "human_verified",
            "observed_entities_ru": "мужчина, кровать",
            "subject_ru": "мужчина",
            "action_ru": "встаёт",
            "object_ru": "кровать",
            "action_sequence_ru": "Мужчина поднимается с кровати и встаёт рядом.",
            "action_start_source_ms": "121000",
            "action_end_source_ms": "124000",
            "evidence_frame_source_ms": "121000;122000;123000",
        }
    )
    audio = dict.fromkeys(REQUIRED_COLUMNS, "")
    audio.update(
        {
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
    )
    return [video, audio]


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_review_labels_validate_against_manifest_pts(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    labels_path = tmp_path / "labels.csv"
    _write_manifest(manifest_path)
    _write_rows(labels_path, _review_rows())

    assert validate_review_labels(labels_path, manifest_path) == ()


def test_review_labels_reject_unlisted_frame_and_unbracketed_audio_transition(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    labels_path = tmp_path / "labels.csv"
    _write_manifest(manifest_path)
    rows = _review_rows()
    rows[0]["evidence_frame_source_ms"] = "120500;122000"
    rows[1]["evidence_audio_source_ms"] = "191000;192000"
    _write_rows(labels_path, rows)

    errors = validate_review_labels(labels_path, manifest_path)

    assert any("sampled source PTS" in error for error in errors)
    assert any("before and after" in error for error in errors)


def test_empty_template_is_invalid_until_two_clips_are_reviewed(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    labels_path = tmp_path / "labels.csv"
    _write_manifest(manifest_path)
    video = dict.fromkeys(REQUIRED_COLUMNS, "")
    video["clip_id"] = "video_01"
    audio = dict.fromkeys(REQUIRED_COLUMNS, "")
    audio["clip_id"] = "audio_01"
    _write_rows(labels_path, [video, audio])

    errors = validate_review_labels(labels_path, manifest_path)

    assert any("verification_status must be" in error for error in errors)


def test_human_verified_audio_requires_a_known_music_state_and_layer(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    labels_path = tmp_path / "labels.csv"
    _write_manifest(manifest_path)
    rows = _review_rows()
    rows[1]["music_layer_type"] = "unknown"
    rows[1]["music_layer_state"] = "unknown"
    rows[1]["transition_start_source_ms"] = ""
    rows[1]["transition_end_source_ms"] = ""
    rows[1]["music_layer_change_ru"] = ""
    _write_rows(labels_path, rows)

    errors = validate_review_labels(labels_path, manifest_path)

    assert any("known music_layer_state" in error for error in errors)
    assert any("known music_layer_type" in error for error in errors)
