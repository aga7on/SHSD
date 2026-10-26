from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from shsd.bridge.dataset import main, validate_jsonl, validate_manifests

_GROUPS = (
    "visual_entities",
    "visual_relations",
    "visual_actions",
    "scene_events",
    "audio_scene",
    "speech_segments",
    "music_layers",
    "av_relations",
    "temporal_relations",
)


def _sample(
    *,
    mode: str = "IMAGE",
    split: str = "train",
    sample_id: str = "sample-1",
    source_group_id: str = "group-1",
    source_id: str = "source-1",
    source_sha256: str = "a" * 64,
) -> dict[str, Any]:
    has_vision, has_audio = mode in {"IMAGE", "VIDEO", "AV"}, mode in {"AUDIO", "AV"}
    frame_pts = [0] if mode == "IMAGE" else [0, 500, 1000, 1500] if has_vision else []
    frames = [{"path": f"frames/{pts}.jpg", "pts_ms": pts} for pts in frame_pts]
    audio = (
        [{"path": "audio.wav", "start_ms": 0, "end_ms": 2000, "sample_rate_hz": 16000}]
        if has_audio
        else []
    )
    target: dict[str, Any] = {
        "visual_entities": [],
        "visual_relations": [],
        "visual_actions": [],
        "scene_events": [],
        "audio_scene": {
            "speech": "unknown",
            "music": "unknown",
            "ambience": "unknown",
            "overlap": "unknown",
        },
        "speech_segments": [],
        "music_layers": [],
        "av_relations": [],
        "temporal_relations": [],
        "coverage": {group: "complete" for group in _GROUPS},
        "caption_ru": "На источнике слышны или видны описанные события.",
    }
    if not has_vision:
        for group in ("visual_entities", "visual_relations", "visual_actions", "scene_events"):
            target["coverage"][group] = "not_applicable"
    if not has_audio:
        target["audio_scene"] = {
            "speech": "unknown",
            "music": "unknown",
            "ambience": "unknown",
            "overlap": "unknown",
        }
        for group in ("audio_scene", "speech_segments", "music_layers"):
            target["coverage"][group] = "not_applicable"
    if mode != "AV":
        target["coverage"]["av_relations"] = "not_applicable"
    if mode == "IMAGE":
        for group in ("visual_actions", "scene_events", "temporal_relations"):
            target["coverage"][group] = "not_applicable"
    if has_vision and mode != "IMAGE":
        target["visual_entities"] = [
            {"entity_id": "person-1", "label_ru": "человек", "evidence_frame_ms": [0, 500]}
        ]
        target["visual_actions"] = [
            {
                "event_id": "action-1",
                "subject_id": "person-1",
                "object_id": None,
                "label_ru": "человек начинает идти",
                "start_ms": 0,
                "end_ms": 500,
                "evidence_frame_ms": [0, 500],
            },
            {
                "event_id": "action-2",
                "subject_id": "person-1",
                "object_id": None,
                "label_ru": "человек продолжает идти",
                "start_ms": 1000,
                "end_ms": 1500,
                "evidence_frame_ms": [1000, 1500],
            },
        ]
        target["temporal_relations"] = [
            {
                "before_event_id": "action-1",
                "after_event_id": "action-2",
                "relation": "before",
            }
        ]
    if has_audio:
        target["audio_scene"]["music"] = "present"
        target["music_layers"] = [
            {
                "event_id": "music-1",
                "label_ru": "музыка с ударными",
                "start_ms": 0,
                "end_ms": 2000,
                "evidence_audio_ms": [500],
            }
        ]
    return {
        "schema_version": 1,
        "sample_id": sample_id,
        "source_id": source_id,
        "source_group_id": source_group_id,
        "source_sha256": source_sha256,
        "epoch": 0,
        "mode": mode,
        "split": split,
        "start_ms": 0,
        "end_ms": 2000,
        "frames": frames,
        "audio": audio,
        "modality_present": {"vision": has_vision, "audio": has_audio},
        "target": target,
        "rights": {
            "license_id": "unit-test",
            "permitted_uses": [
                {"train": "train", "val": "validation", "test": "evaluation"}[split]
            ],
        },
        "annotation": {
            "verification": "human_verified",
            "annotator_id": "unit-test-annotator",
            "guide_version": "unit-test-v1",
        },
    }


def _write_manifest(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")


def test_valid_image_video_audio_and_av_records(tmp_path: Path) -> None:
    for mode in ("IMAGE", "VIDEO", "AUDIO", "AV"):
        path = tmp_path / f"{mode}.jsonl"
        _write_manifest(path, [_sample(mode=mode)])
        report = validate_jsonl(path)
        assert report.valid, (mode, report.errors)


def test_video_action_requires_exact_sampled_pts_and_known_entity(tmp_path: Path) -> None:
    record = _sample(mode="VIDEO")
    record["target"]["visual_actions"][0]["evidence_frame_ms"] = [0, 999]
    record["target"]["visual_actions"][1]["subject_id"] = "unknown"
    path = tmp_path / "invalid-evidence.jsonl"
    _write_manifest(path, [record])

    report = validate_jsonl(path)

    assert any("sampled source PTS" in error for error in report.errors)
    assert any("unknown subject_id" in error for error in report.errors)


def test_video_action_needs_two_distinct_sampled_pts(tmp_path: Path) -> None:
    record = _sample(mode="VIDEO")
    record["target"]["visual_actions"][0]["evidence_frame_ms"] = [0, 0]
    path = tmp_path / "duplicate-evidence.jsonl"
    _write_manifest(path, [record])

    report = validate_jsonl(path)

    assert any("at least two sampled PTS values" in error for error in report.errors)
    assert any("evidence timestamps must be unique" in error for error in report.errors)


def test_video_frame_pts_must_be_strictly_increasing(tmp_path: Path) -> None:
    record = _sample(mode="VIDEO")
    record["frames"][2]["pts_ms"] = 500
    path = tmp_path / "unordered-frames.jsonl"
    _write_manifest(path, [record])

    report = validate_jsonl(path)

    assert any("strictly increasing" in error for error in report.errors)


def test_malformed_temporal_event_ids_are_reported_without_crashing(tmp_path: Path) -> None:
    record = _sample(mode="VIDEO")
    record["target"]["temporal_relations"][0]["before_event_id"] = {"not": "an id"}
    path = tmp_path / "malformed-relation.jsonl"
    _write_manifest(path, [record])

    report = validate_jsonl(path)

    assert any(
        "temporal relation references an unknown event_id" in error for error in report.errors
    )


@pytest.mark.parametrize(
    ("relation", "reverse_intervals", "should_pass"),
    [
        ("before", False, True),
        ("before", True, False),
        ("overlaps", False, False),
    ],
)
def test_temporal_relations_must_match_event_intervals(
    tmp_path: Path, relation: str, reverse_intervals: bool, should_pass: bool
) -> None:
    record = _sample(mode="VIDEO")
    record["target"]["temporal_relations"][0]["relation"] = relation
    if reverse_intervals:
        record["target"]["temporal_relations"][0]["before_event_id"] = "action-2"
        record["target"]["temporal_relations"][0]["after_event_id"] = "action-1"
    path = tmp_path / "temporal.jsonl"
    _write_manifest(path, [record])

    report = validate_jsonl(path)

    assert report.valid is should_pass
    if not should_pass:
        assert any("does not match the event intervals" in error for error in report.errors)


@pytest.mark.parametrize("identity_field", ["source_group_id", "source_id", "source_sha256"])
def test_cross_manifest_source_leakage_is_rejected(tmp_path: Path, identity_field: str) -> None:
    records = {
        split: _sample(
            split=split,
            sample_id=f"sample-{split}",
            source_group_id=f"group-{split}",
            source_id=f"source-{split}",
            source_sha256=(f"{index:x}" * 64),
        )
        for index, split in enumerate(("train", "val", "test"), start=1)
    }
    records["val"][identity_field] = records["train"][identity_field]
    paths: dict[str, Path] = {}
    for split, record in records.items():
        path = tmp_path / f"{split}.jsonl"
        _write_manifest(path, [record])
        paths[split] = path

    report = validate_manifests(paths)

    assert any(
        f"{identity_field} " in error and "leaks across train/val" in error
        for error in report.errors
    )


@pytest.mark.parametrize("identity_field", ["source_group_id", "source_id"])
def test_cross_manifest_leakage_normalizes_identity_whitespace(
    tmp_path: Path, identity_field: str
) -> None:
    paths: dict[str, Path] = {}
    for split in ("train", "val", "test"):
        record = _sample(
            split=split,
            sample_id=f"sample-{split}",
            source_group_id=f"group-{split}",
            source_id=f"source-{split}",
            source_sha256=("a" if split == "train" else "b" if split == "val" else "c") * 64,
        )
        if split == "train":
            record[identity_field] = "shared-source"
        elif split == "val":
            record[identity_field] = " shared-source "
        path = tmp_path / f"{split}.jsonl"
        _write_manifest(path, [record])
        paths[split] = path

    report = validate_manifests(paths)

    assert any(
        f"{identity_field} shared-source leaks across train/val" in error for error in report.errors
    )


def test_manifest_split_mismatch_and_duplicate_sample_id_are_rejected(tmp_path: Path) -> None:
    paths: dict[str, Path] = {}
    for split in ("train", "val", "test"):
        record = _sample(split=split, sample_id="duplicate" if split != "test" else "test-only")
        path = tmp_path / f"{split}.jsonl"
        _write_manifest(path, [record])
        paths[split] = path
    val_record = _sample(
        split="train",
        sample_id="duplicate",
        source_group_id="group-elsewhere",
        source_id="source-elsewhere",
        source_sha256="b" * 64,
    )
    _write_manifest(paths["val"], [val_record])

    report = validate_manifests(paths)

    assert any("does not match its manifest" in error for error in report.errors)
    assert any(
        "sample_id duplicate is duplicated across train/val" in error for error in report.errors
    )


def test_disjoint_train_val_test_sources_are_accepted_and_cli_uses_all_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    paths: dict[str, Path] = {}
    for split in ("train", "val", "test"):
        path = tmp_path / f"{split}.jsonl"
        _write_manifest(
            path,
            [
                _sample(
                    split=split,
                    sample_id=f"sample-{split}",
                    source_group_id=f"group-{split}",
                    source_id=f"source-{split}",
                    source_sha256=({"train": "a", "val": "b", "test": "c"}[split] * 64),
                )
            ],
        )
        paths[split] = path

    report = validate_manifests(paths)
    assert report.valid

    monkeypatch.setattr(
        "sys.argv",
        [
            "validate_bridge_dataset",
            "--train",
            str(paths["train"]),
            "--val",
            str(paths["val"]),
            "--test",
            str(paths["test"]),
        ],
    )
    assert main() == 0
    assert "VALID: 3 source-separated across train/val/test" in capsys.readouterr().out


def test_manifest_validator_requires_train_val_and_test() -> None:
    report = validate_manifests({"train": Path("train.jsonl"), "test": Path("test.jsonl")})
    assert not report.valid
    assert "missing val" in report.errors[0]


def test_missing_modality_requires_empty_targets_and_not_applicable_coverage(
    tmp_path: Path,
) -> None:
    record = _sample(mode="AUDIO")
    record["target"]["visual_entities"] = [
        {"entity_id": "invented", "label_ru": "человек", "evidence_frame_ms": [0]}
    ]
    path = tmp_path / "audio-with-visual-claim.jsonl"
    _write_manifest(path, [record])

    report = validate_jsonl(path)

    assert any("visual_entities must be empty/unknown" in error for error in report.errors)
