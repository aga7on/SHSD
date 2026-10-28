"""Validate F10 JSONL manifests before evaluation or training."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, TypeGuard

_PRESENCE = {"present", "absent", "unknown"}
_COVERAGE = {"complete", "partial", "not_applicable"}
_SPLIT_USE = {"train": "train", "val": "validation", "test": "evaluation"}
_FIELDS = {
    "visual_entities": "vision",
    "visual_relations": "vision",
    "visual_actions": "vision",
    "scene_events": "vision",
    "audio_scene": "audio",
    "speech_segments": "audio",
    "music_layers": "audio",
    "av_relations": "av",
    "temporal_relations": "temporal",
}


@dataclass(frozen=True, slots=True)
class DatasetReport:
    samples: int
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors


def _object(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _array(value: Any) -> list[Any] | None:
    return value if isinstance(value, list) else None


def _integer(value: Any) -> TypeGuard[int]:
    """Narrow ``Any`` JSON values to a real ``int`` (bools are not integers here)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _has_text(value: Any) -> TypeGuard[str]:
    """Narrow ``Any`` JSON values to a non-empty string."""
    return isinstance(value, str) and bool(value.strip())


def _within_sample(
    item: dict[str, Any], start_ms: int, end_ms: int, label: str, errors: list[str]
) -> None:
    item_start, item_end = item.get("start_ms"), item.get("end_ms")
    if not _integer(item_start) or not _integer(item_end):
        errors.append(f"{label}: start_ms/end_ms must be integers")
    elif not start_ms <= item_start < item_end <= end_ms:
        errors.append(f"{label}: interval must be within the sample interval")


def _validate_sample(
    sample: Any, line_number: int, media_root: Path | None
) -> tuple[list[str], str | None, str | None]:
    errors: list[str] = []
    prefix = f"line {line_number}"
    record = _object(sample)
    if record is None:
        return [f"{prefix}: sample must be a JSON object"], None, None

    sample_id = record.get("sample_id")
    if not _has_text(sample_id):
        errors.append(f"{prefix}: sample_id must be non-empty")
        sample_id = None
    else:
        if sample_id != sample_id.strip():
            errors.append(f"{prefix}: sample_id must not have leading or trailing whitespace")
        sample_id = sample_id.strip()
    mode, split = record.get("mode"), record.get("split")
    if not _integer(record.get("schema_version")) or record["schema_version"] != 1:
        errors.append(f"{prefix}: schema_version must be 1")
    if not _integer(record.get("epoch")) or record["epoch"] < 0:
        errors.append(f"{prefix}: epoch must be a non-negative integer")
    if not isinstance(mode, str) or mode not in {"IMAGE", "VIDEO", "AUDIO", "AV"}:
        errors.append(f"{prefix}: mode must be IMAGE, VIDEO, AUDIO, or AV")
        mode = None
    if not isinstance(split, str) or split not in _SPLIT_USE:
        errors.append(f"{prefix}: split must be train, val, or test")
        split = None

    source_group_id = record.get("source_group_id")
    if not _has_text(source_group_id):
        errors.append(f"{prefix}: source_group_id is required for source-separated splits")
        source_group_id = None
    else:
        if source_group_id != source_group_id.strip():
            errors.append(f"{prefix}: source_group_id must not have leading or trailing whitespace")
        source_group_id = source_group_id.strip()
    source_id = record.get("source_id")
    if not _has_text(source_id):
        errors.append(f"{prefix}: source_id must be non-empty")
    elif source_id != source_id.strip():
        errors.append(f"{prefix}: source_id must not have leading or trailing whitespace")
    digest = record.get("source_sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
        errors.append(f"{prefix}: source_sha256 must contain 64 hexadecimal characters")

    start_ms, end_ms = record.get("start_ms"), record.get("end_ms")
    interval_valid = _integer(start_ms) and _integer(end_ms) and 0 <= start_ms < end_ms
    if not interval_valid:
        errors.append(f"{prefix}: interval must satisfy integer 0 <= start_ms < end_ms")
        start_ms, end_ms = 0, 0

    frames = _array(record.get("frames"))
    audio = _array(record.get("audio"))
    if frames is None or audio is None:
        errors.append(f"{prefix}: frames and audio must be arrays")
        frames, audio = [], []
    mask = _object(record.get("modality_present"))
    if mask is None or any(not isinstance(mask.get(key), bool) for key in ("vision", "audio")):
        errors.append(f"{prefix}: modality_present must contain boolean vision and audio keys")
        mask = {"vision": False, "audio": False}

    expected = (
        {
            "IMAGE": (1, 1, 0, 0, True, False),
            "VIDEO": (2, None, 0, 0, True, False),
            "AUDIO": (0, 0, 1, None, False, True),
            "AV": (1, None, 1, None, True, True),
        }.get(mode)
        if isinstance(mode, str)
        else None
    )
    if expected:
        f_min, f_max, a_min, a_max, vision_on, audio_on = expected
        if len(frames) < f_min or (f_max is not None and len(frames) > f_max):
            errors.append(f"{prefix}: {mode} requires {f_min}..{f_max or 'many'} frame(s)")
        if len(audio) < a_min or (a_max is not None and len(audio) > a_max):
            errors.append(f"{prefix}: {mode} has an invalid number of audio chunks")
        if mask.get("vision") is not vision_on or mask.get("audio") is not audio_on:
            errors.append(f"{prefix}: modality_present does not match mode {mode}")

    frame_pts: list[int] = []
    for index, frame in enumerate(frames):
        item = _object(frame)
        if item is None or not _has_text(item.get("path")) or not _integer(item.get("pts_ms")):
            errors.append(f"{prefix}: frames[{index}] needs path and integer pts_ms")
            continue
        pts_ms = item["pts_ms"]
        frame_pts.append(pts_ms)
        if interval_valid and not start_ms <= pts_ms < end_ms:
            errors.append(f"{prefix}: frame PTS {pts_ms} is outside the sample interval")
        _validate_media_path(item["path"], media_root, f"{prefix}: frames[{index}]", errors)
    if any(left >= right for left, right in zip(frame_pts, frame_pts[1:], strict=False)):
        errors.append(f"{prefix}: frame PTS values must be strictly increasing")

    audio_intervals: list[tuple[int, int]] = []
    for index, chunk in enumerate(audio):
        item = _object(chunk)
        if item is None or not _has_text(item.get("path")):
            errors.append(f"{prefix}: audio[{index}] needs a path")
            continue
        _validate_media_path(item["path"], media_root, f"{prefix}: audio[{index}]", errors)
        a_start, a_end = item.get("start_ms"), item.get("end_ms")
        if not _integer(item.get("sample_rate_hz")) or item["sample_rate_hz"] <= 0:
            errors.append(f"{prefix}: audio[{index}].sample_rate_hz must be positive")
        if (
            not _integer(a_start)
            or not _integer(a_end)
            or not interval_valid
            or not start_ms <= a_start < a_end <= end_ms
        ):
            errors.append(f"{prefix}: audio[{index}] interval must be within the sample interval")
        else:
            audio_intervals.append((a_start, a_end))

    target = _object(record.get("target"))
    if target is None:
        errors.append(f"{prefix}: target must be an object")
        target = {}
    coverage = _object(target.get("coverage"))
    if coverage is None:
        errors.append(f"{prefix}: target.coverage must declare completeness for every target group")
        coverage = {}

    for field, applicability in _FIELDS.items():
        value = target.get(field)
        if field == "audio_scene":
            audio_scene = _object(value)
            if audio_scene is None or any(
                not isinstance(audio_scene.get(key), str) or audio_scene.get(key) not in _PRESENCE
                for key in ("speech", "music", "ambience", "overlap")
            ):
                errors.append(
                    f"{prefix}: audio_scene must use present/absent/unknown for speech, music, "
                    "ambience, and overlap"
                )
                audio_scene = {}
            values_empty = all(
                audio_scene.get(key) == "unknown"
                for key in ("speech", "music", "ambience", "overlap")
            )
        else:
            items = _array(value)
            if items is None:
                errors.append(f"{prefix}: target.{field} must be an array")
                items = []
            values_empty = not items
        state = coverage.get(field)
        if not isinstance(state, str) or state not in _COVERAGE:
            errors.append(
                f"{prefix}: target.coverage.{field} must be complete, partial, or not_applicable"
            )
        absent = (
            (applicability == "vision" and not mask.get("vision"))
            or (applicability == "audio" and not mask.get("audio"))
            or (applicability == "av" and mode != "AV")
            or (applicability == "temporal" and mode == "IMAGE")
        )
        if mode == "IMAGE" and field in {"visual_actions", "scene_events", "temporal_relations"}:
            absent = True
        if absent and (state != "not_applicable" or not values_empty):
            errors.append(
                f"{prefix}: {field} must be empty/unknown and not_applicable when its modality "
                "is unavailable"
            )
        if state == "not_applicable" and not values_empty:
            errors.append(f"{prefix}: {field} has labels but coverage is not_applicable")

    if not _has_text(target.get("caption_ru")):
        errors.append(f"{prefix}: target.caption_ru must be non-empty Russian narration text")

    entity_ids: set[str] = set()
    for entity in _array(target.get("visual_entities")) or []:
        item = _object(entity)
        if (
            item is None
            or not _has_text(item.get("entity_id"))
            or not _has_text(item.get("label_ru"))
        ):
            errors.append(f"{prefix}: each visual entity needs entity_id and label_ru")
            continue
        if item["entity_id"] in entity_ids:
            errors.append(f"{prefix}: duplicate visual entity_id {item['entity_id']}")
        entity_ids.add(item["entity_id"])
        _validate_evidence_times(
            item.get("evidence_frame_ms"),
            frame_pts,
            f"{prefix}: visual entity {item['entity_id']}",
            errors,
        )

    events: dict[str, tuple[int | None, int | None]] = {}
    event_intervals: dict[str, tuple[Any, Any]] = {}
    audio_event_ids: set[str] = set()
    for field in ("visual_actions", "scene_events"):
        for event in _array(target.get(field)) or []:
            item = _object(event)
            if item is None or not _has_text(item.get("event_id")):
                errors.append(f"{prefix}: each {field} record needs event_id")
                continue
            event_id = item["event_id"]
            if event_id in events:
                errors.append(f"{prefix}: duplicate event_id {event_id}")
            events[event_id] = (item.get("start_ms"), item.get("end_ms"))
            if event_id in audio_event_ids:
                errors.append(f"{prefix}: event_id {event_id} is used by visual and audio events")
            event_intervals[event_id] = (item.get("start_ms"), item.get("end_ms"))
            if interval_valid:
                _within_sample(item, start_ms, end_ms, f"{prefix}: {field} {event_id}", errors)
            if field == "visual_actions":
                if (
                    not _has_text(item.get("subject_id"))
                    or item.get("subject_id") not in entity_ids
                ):
                    errors.append(f"{prefix}: action {event_id} references an unknown subject_id")
                if item.get("object_id") is not None and (
                    not _has_text(item.get("object_id")) or item.get("object_id") not in entity_ids
                ):
                    errors.append(f"{prefix}: action {event_id} references an unknown object_id")
                evidence = item.get("evidence_frame_ms")
                _validate_evidence_times(
                    evidence, frame_pts, f"{prefix}: visual action {event_id}", errors
                )
                if mode in {"VIDEO", "AV"} and (
                    not isinstance(evidence, list)
                    or len({timestamp for timestamp in evidence if _integer(timestamp)}) < 2
                ):
                    errors.append(
                        f"{prefix}: video actions require evidence from at least two sampled "
                        "PTS values"
                    )
            elif item.get("entity_id") is not None and (
                not _has_text(item.get("entity_id")) or item.get("entity_id") not in entity_ids
            ):
                errors.append(f"{prefix}: scene event {event_id} references an unknown entity_id")
            if field == "scene_events":
                _validate_evidence_times(
                    item.get("evidence_frame_ms"),
                    frame_pts,
                    f"{prefix}: scene event {event_id}",
                    errors,
                )

    for relation in _array(target.get("visual_relations")) or []:
        item = _object(relation)
        if item is None:
            continue
        for entity_key in ("subject_id", "object_id"):
            if not _has_text(item.get(entity_key)) or item.get(entity_key) not in entity_ids:
                errors.append(f"{prefix}: visual relation references an unknown {entity_key}")
        _validate_evidence_times(
            item.get("evidence_frame_ms"), frame_pts, f"{prefix}: visual relation", errors
        )

    for field in ("speech_segments", "music_layers"):
        for event in _array(target.get(field)) or []:
            item = _object(event)
            if item is None or not _has_text(item.get("event_id")):
                errors.append(f"{prefix}: each {field} record needs event_id")
                continue
            event_id = item["event_id"]
            if event_id in audio_event_ids:
                errors.append(f"{prefix}: duplicate audio event_id {event_id}")
            elif event_id in events:
                errors.append(f"{prefix}: event_id {event_id} is used by visual and audio events")
            audio_event_ids.add(event_id)
            event_intervals[event_id] = (item.get("start_ms"), item.get("end_ms"))
            if interval_valid:
                _within_sample(item, start_ms, end_ms, f"{prefix}: {field} {event_id}", errors)
            evidence = item.get("evidence_audio_ms")
            if not isinstance(evidence, list) or not evidence:
                errors.append(f"{prefix}: {field} {event_id} needs audio evidence timestamps")
            elif any(
                not _integer(ts) or not any(a <= ts < b for a, b in audio_intervals)
                for ts in evidence
            ):
                errors.append(
                    f"{prefix}: {field} {event_id} has evidence outside the supplied audio chunks"
                )

    for relation in _array(target.get("av_relations")) or []:
        item = _object(relation)
        if item is None:
            continue
        if not _has_text(item.get("visual_event_id")) or item.get("visual_event_id") not in events:
            errors.append(f"{prefix}: AV relation references an unknown visual event/entity")
        if (
            not _has_text(item.get("audio_event_id"))
            or item.get("audio_event_id") not in audio_event_ids
        ):
            errors.append(f"{prefix}: AV relation references an unknown audio event")
        refs = item.get("evidence_refs")
        if not isinstance(refs, list) or len(refs) < 2:
            errors.append(
                f"{prefix}: AV relation needs separate visual and audio evidence references"
            )
        else:
            frame_refs: set[int] = set()
            audio_refs: set[int] = set()
            for ref in refs:
                if not isinstance(ref, str) or ":" not in ref:
                    continue
                prefix_name, raw_ms = ref.split(":", maxsplit=1)
                if not raw_ms.isdecimal():
                    continue
                if prefix_name == "frame":
                    frame_refs.add(int(raw_ms))
                elif prefix_name == "audio":
                    audio_refs.add(int(raw_ms))
            valid_frame_ref = bool(frame_refs.intersection(frame_pts))
            valid_audio_ref = any(
                start <= timestamp < end
                for timestamp in audio_refs
                for start, end in audio_intervals
            )
            if not valid_frame_ref or not valid_audio_ref:
                errors.append(
                    f"{prefix}: AV relation must reference an available frame:<PTS> and audio:<ms>"
                )

    for relation in _array(target.get("temporal_relations")) or []:
        item = _object(relation)
        if item is None:
            continue
        before, after = item.get("before_event_id"), item.get("after_event_id")
        known_events = set(events) | audio_event_ids
        if (
            not _has_text(before)
            or not _has_text(after)
            or before not in known_events
            or after not in known_events
        ):
            errors.append(f"{prefix}: temporal relation references an unknown event_id")
        if before == after:
            errors.append(f"{prefix}: temporal relation cannot point an event to itself")
        relation_label = item.get("relation")
        if not isinstance(relation_label, str) or relation_label not in {
            "before",
            "overlaps",
            "starts_within",
            "ends_within",
        }:
            errors.append(f"{prefix}: temporal relation has an unsupported relation label")
            continue
        if (
            _has_text(before)
            and _has_text(after)
            and before in event_intervals
            and after in event_intervals
        ):
            before_start, before_end = event_intervals[before]
            after_start, after_end = event_intervals[after]
            if (
                not all(
                    _integer(value) for value in (before_start, before_end, after_start, after_end)
                )
                or before_start >= before_end
                or after_start >= after_end
            ):
                errors.append(f"{prefix}: temporal relation needs valid event intervals")
                continue
            matches = {
                "before": before_end <= after_start,
                "overlaps": before_start < after_end and after_start < before_end,
                "starts_within": before_start <= after_start < before_end,
                "ends_within": before_start < after_end <= before_end,
            }[relation_label]
            if not matches:
                errors.append(
                    f"{prefix}: temporal relation {relation_label} does not match "
                    "the event intervals"
                )

    rights = _object(record.get("rights"))
    if rights is None or not _has_text(rights.get("license_id")):
        errors.append(f"{prefix}: rights.license_id is required")
    else:
        uses = rights.get("permitted_uses")
        if not isinstance(uses, list) or (
            isinstance(split, str) and split in _SPLIT_USE and _SPLIT_USE[split] not in uses
        ):
            errors.append(f"{prefix}: license does not document permitted use for split {split}")
    annotation = _object(record.get("annotation"))
    if annotation is None or annotation.get("verification") != "human_verified":
        errors.append(f"{prefix}: training/evaluation samples must be independently human-verified")
    elif not _has_text(annotation.get("annotator_id")) or not _has_text(
        annotation.get("guide_version")
    ):
        errors.append(f"{prefix}: human-verified samples require annotator_id and guide_version")

    return (
        errors,
        sample_id if isinstance(sample_id, str) else None,
        source_group_id if isinstance(source_group_id, str) else None,
    )


def _validate_media_path(path: str, media_root: Path | None, label: str, errors: list[str]) -> None:
    posix, windows = PurePosixPath(path), PureWindowsPath(path)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or ".." in posix.parts
        or ".." in windows.parts
    ):
        errors.append(f"{label}: media path must be relative and stay under the media root")
        return
    if media_root is not None:
        resolved_root = media_root.resolve()
        relative_parts = windows.parts if "\\" in path else posix.parts
        resolved_path = (resolved_root / Path(*relative_parts)).resolve()
        if not resolved_path.is_relative_to(resolved_root):
            errors.append(f"{label}: media path escapes the media root")
        elif not resolved_path.is_file():
            errors.append(f"{label}: media file does not exist: {path}")


def _validate_evidence_times(
    value: Any, available: list[int], label: str, errors: list[str]
) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{label}: evidence timestamps are required")
    elif any(not _integer(ts) or ts not in available for ts in value):
        errors.append(f"{label}: evidence_frame_ms must reference sampled source PTS values")
    elif len(set(value)) != len(value):
        errors.append(f"{label}: evidence timestamps must be unique")


def validate_jsonl(path: Path, *, media_root: Path | None = None) -> DatasetReport:
    """Validate records, temporal evidence, rights, and source-separated splits."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    source_splits: dict[str, str] = {}
    samples = 0
    try:
        stream = path.open("r", encoding="utf-8")
    except OSError as exc:
        return DatasetReport(0, (f"cannot open {path}: {exc}",))
    with stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            samples += 1
            try:
                sample = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
                continue
            sample_errors, sample_id, source_group_id = _validate_sample(
                sample, line_number, media_root
            )
            errors.extend(sample_errors)
            record = _object(sample)
            split = record.get("split") if record else None
            if sample_id:
                if sample_id in seen_ids:
                    errors.append(f"line {line_number}: duplicate sample_id {sample_id}")
                seen_ids.add(sample_id)
            if source_group_id and isinstance(split, str) and split in _SPLIT_USE:
                previous = source_splits.setdefault(source_group_id, split)
                if previous != split:
                    errors.append(
                        f"line {line_number}: source_group_id {source_group_id} leaks across "
                        f"{previous}/{split}"
                    )
    if samples == 0:
        errors.append("dataset contains no JSONL samples")
    return DatasetReport(samples, tuple(errors))


def validate_manifests(
    manifests: Mapping[str, Path], *, media_roots: Mapping[str, Path] | None = None
) -> DatasetReport:
    """Validate train/val/test manifests and reject cross-split source leakage."""
    required_splits = {"train", "val", "test"}
    if set(manifests) != required_splits:
        missing = sorted(required_splits - set(manifests))
        extra = sorted(set(manifests) - required_splits)
        errors = []
        if missing:
            errors.append(
                f"manifests must include train, val, and test; missing {', '.join(missing)}"
            )
        if extra:
            errors.append(f"unsupported manifest split(s): {', '.join(extra)}")
        return DatasetReport(0, tuple(errors))

    errors: list[str] = []
    samples = 0
    seen_sample_ids: dict[str, str] = {}
    seen_sources: dict[tuple[str, str], tuple[str, str]] = {}
    for expected_split in ("train", "val", "test"):
        path = manifests[expected_split]
        report = validate_jsonl(
            path,
            media_root=(media_roots or {}).get(expected_split),
        )
        samples += report.samples
        errors.extend(f"{expected_split}: {error}" for error in report.errors)
        try:
            stream = path.open("r", encoding="utf-8")
        except OSError:
            continue  # validate_jsonl has already reported the open failure.
        with stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    record = _object(json.loads(line))
                except json.JSONDecodeError:
                    continue  # validate_jsonl has already reported malformed JSON.
                if record is None:
                    continue
                location = f"{expected_split} line {line_number}"
                declared_split = record.get("split")
                if declared_split != expected_split:
                    errors.append(
                        f"{location}: record split {declared_split!r} does not match its manifest"
                    )
                sample_id = record.get("sample_id")
                if _has_text(sample_id):
                    sample_id = sample_id.strip()
                    previous_split = seen_sample_ids.setdefault(sample_id, expected_split)
                    if previous_split != expected_split:
                        errors.append(
                            f"{location}: sample_id {sample_id} is duplicated across "
                            f"{previous_split}/{expected_split}"
                        )
                for field in ("source_group_id", "source_id", "source_sha256"):
                    value = record.get(field)
                    if not _has_text(value):
                        continue
                    normalized = value.strip()
                    if field == "source_sha256":
                        normalized = normalized.casefold()
                    identity = (field, normalized)
                    previous = seen_sources.setdefault(identity, (expected_split, location))
                    if previous[0] != expected_split:
                        errors.append(
                            f"{location}: {field} {normalized} leaks across "
                            f"{previous[0]}/{expected_split}"
                        )
    return DatasetReport(samples, tuple(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?", help="single JSONL manifest to validate")
    parser.add_argument(
        "--media-root", type=Path, help="also check referenced files under this root"
    )
    parser.add_argument("--train", type=Path, help="train JSONL manifest")
    parser.add_argument("--val", type=Path, help="validation JSONL manifest")
    parser.add_argument("--test", type=Path, help="held-out test JSONL manifest")
    args = parser.parse_args()
    multi_paths = {name: getattr(args, name) for name in ("train", "val", "test")}
    supplied_multi = {name: path for name, path in multi_paths.items() if path is not None}
    if supplied_multi:
        if args.manifest is not None or len(supplied_multi) != 3:
            parser.error("provide either one positional manifest or all of --train, --val, --test")
        roots = {name: args.media_root for name in supplied_multi if args.media_root is not None}
        report = validate_manifests(supplied_multi, media_roots=roots)
        report_label = "source-separated across train/val/test, human-verified"
    else:
        if args.manifest is None:
            parser.error("provide a manifest or all of --train, --val, --test")
        report = validate_jsonl(args.manifest, media_root=args.media_root)
        report_label = "human-verified"
    for error in report.errors:
        print(f"ERROR: {error}")
    if report.valid:
        print(f"VALID: {report.samples} {report_label} sample(s)")
        return 0
    print(f"INVALID: {report.samples} sample(s), {len(report.errors)} error(s)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
