"""Validate blind-review CSV labels against the F10 clip manifest and source PTS."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = DEFAULT_ROOT / "benchmarks/review/bridge_f10_examples/review_manifest.json"
DEFAULT_LABELS = DEFAULT_ROOT / "benchmarks/review/bridge_f10_examples/human_labels_template.csv"
REQUIRED_COLUMNS = (
    "clip_id",
    "reviewer_id",
    "guide_version",
    "verification_status",
    "observed_entities_ru",
    "subject_ru",
    "action_ru",
    "object_ru",
    "action_sequence_ru",
    "action_start_source_ms",
    "action_end_source_ms",
    "evidence_frame_source_ms",
    "audio_scene_ru",
    "music_layer_type",
    "music_layer_state",
    "music_layer_change_ru",
    "transition_start_source_ms",
    "transition_end_source_ms",
    "evidence_audio_source_ms",
    "notes",
)
_VERIFICATION_STATES = {"human_verified", "partial", "unverified"}
_MUSIC_LAYER_TYPES = {
    "vocal",
    "percussion",
    "bass",
    "instrument_family",
    "music_presence",
    "unknown",
}
_MUSIC_LAYER_STATES = {"none", "present", "onset", "offset", "changed", "unknown"}
_TRANSITION_STATES = {"onset", "offset", "changed"}


def _integer(raw: str, label: str, errors: list[str], *, required: bool) -> int | None:
    value = raw.strip()
    if not value:
        if required:
            errors.append(f"{label}: value is required")
        return None
    try:
        return int(value)
    except ValueError:
        errors.append(f"{label}: expected integer milliseconds")
        return None


def _timestamps(raw: str, label: str, errors: list[str]) -> list[int]:
    values = raw.strip()
    if not values:
        return []
    parsed: list[int] = []
    for value in values.split(";"):
        try:
            parsed.append(int(value.strip()))
        except ValueError:
            errors.append(f"{label}: use semicolon-separated integer milliseconds")
            return []
    if len(set(parsed)) != len(parsed):
        errors.append(f"{label}: timestamps must be unique")
    return parsed


def _clip_bounds(clip: dict[str, Any], label: str, errors: list[str]) -> tuple[int, int] | None:
    interval = clip.get("original_source_interval_ms")
    if (
        not isinstance(interval, list)
        or len(interval) != 2
        or any(not isinstance(value, int) for value in interval)
        or interval[0] >= interval[1]
    ):
        errors.append(f"manifest {label}: invalid original_source_interval_ms")
        return None
    return interval[0], interval[1]


def _validate_video(row: dict[str, str], clip: dict[str, Any], errors: list[str]) -> None:
    bounds = _clip_bounds(clip, "video", errors)
    start = _integer(
        row.get("action_start_source_ms", ""),
        "video action_start_source_ms",
        errors,
        required=row.get("verification_status") == "human_verified",
    )
    end = _integer(
        row.get("action_end_source_ms", ""),
        "video action_end_source_ms",
        errors,
        required=row.get("verification_status") == "human_verified",
    )
    if start is not None and end is not None:
        if start >= end:
            errors.append("video action interval must have start before end")
        if bounds is not None and (start < bounds[0] or end > bounds[1]):
            errors.append("video action interval must stay within the original source clip")

    allowed_pts = clip.get("review_frame_pts_ms")
    if not isinstance(allowed_pts, list) or any(
        not isinstance(value, int) for value in allowed_pts
    ):
        errors.append("manifest video: review_frame_pts_ms must be integer timestamps")
        allowed_pts = []
    evidence = _timestamps(
        row.get("evidence_frame_source_ms", ""), "video evidence_frame_source_ms", errors
    )
    if row.get("verification_status") == "human_verified" and len(evidence) < 2:
        errors.append("human-verified video action needs at least two evidence frame PTS values")
    if any(value not in allowed_pts for value in evidence):
        errors.append("video evidence must use sampled source PTS values from the manifest")
    if (
        start is not None
        and end is not None
        and any(not start <= value < end for value in evidence)
    ):
        errors.append("video action evidence PTS must fall within its action interval")

    if row.get("verification_status") == "human_verified":
        for field in (
            "observed_entities_ru",
            "subject_ru",
            "action_ru",
            "object_ru",
            "action_sequence_ru",
        ):
            if not row.get(field, "").strip():
                errors.append(f"human-verified video action requires {field}")


def _validate_audio(row: dict[str, str], clip: dict[str, Any], errors: list[str]) -> None:
    bounds = _clip_bounds(clip, "audio", errors)
    state = row.get("music_layer_state", "").strip()
    layer_type = row.get("music_layer_type", "").strip()
    if state and state not in _MUSIC_LAYER_STATES:
        errors.append("audio music_layer_state has an unsupported value")
    if layer_type and layer_type not in _MUSIC_LAYER_TYPES:
        errors.append("audio music_layer_type has an unsupported value")

    start = _integer(
        row.get("transition_start_source_ms", ""),
        "audio transition_start_source_ms",
        errors,
        required=False,
    )
    end = _integer(
        row.get("transition_end_source_ms", ""),
        "audio transition_end_source_ms",
        errors,
        required=False,
    )
    if (start is None) != (end is None):
        errors.append("audio transition start and end must either both be set or both be blank")
    if start is not None and end is not None:
        if start >= end:
            errors.append("audio transition interval must have start before end")
        if bounds is not None and (start < bounds[0] or end > bounds[1]):
            errors.append("audio transition interval must stay within the original source clip")
        if state not in _TRANSITION_STATES:
            errors.append("audio transition times require music_layer_state onset/offset/changed")
        if not row.get("music_layer_change_ru", "").strip():
            errors.append("audio transition times require music_layer_change_ru")
        if layer_type in {"", "unknown"}:
            errors.append("audio transition needs a music_layer_type")

    evidence = _timestamps(
        row.get("evidence_audio_source_ms", ""), "audio evidence_audio_source_ms", errors
    )
    if row.get("verification_status") == "human_verified" and len(evidence) < 2:
        errors.append("human-verified audio scene needs at least two evidence audio PTS values")
    if bounds is not None and any(not bounds[0] <= value < bounds[1] for value in evidence):
        errors.append("audio evidence PTS must stay within the original source clip")
    if (
        start is not None
        and end is not None
        and not (
            any(value < start for value in evidence) and any(value >= end for value in evidence)
        )
    ):
        errors.append("audio transition evidence needs at least one PTS before and after it")

    if (
        row.get("verification_status") == "human_verified"
        and not row.get("audio_scene_ru", "").strip()
    ):
        errors.append("human-verified audio row requires audio_scene_ru")
    if row.get("verification_status") == "human_verified":
        if state not in _MUSIC_LAYER_STATES - {"unknown"}:
            errors.append("human-verified audio row requires a known music_layer_state")
        if layer_type not in _MUSIC_LAYER_TYPES - {"unknown"}:
            errors.append("human-verified audio row requires a known music_layer_type")


def validate_review_labels(labels_path: Path, manifest_path: Path) -> tuple[str, ...]:
    """Return label and timestamp errors; an unfilled template is intentionally invalid."""
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (f"cannot read review manifest: {exc}",)

    guide = manifest.get("review_guide")
    guide_version = guide.get("guide_version") if isinstance(guide, dict) else None
    clips: dict[str, dict[str, Any]] = {}
    for name in ("video", "audio"):
        clip = manifest.get(name)
        if not isinstance(clip, dict):
            errors.append(f"manifest is missing {name} clip")
            continue
        clips[f"{name}_01"] = clip

    try:
        with labels_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                return ("review CSV has no header",)
            if len(reader.fieldnames) != len(set(reader.fieldnames)):
                errors.append("review CSV header contains duplicate columns")
            missing = sorted(set(REQUIRED_COLUMNS) - set(reader.fieldnames))
            extra = sorted(set(reader.fieldnames) - set(REQUIRED_COLUMNS))
            if missing:
                errors.append(f"review CSV is missing columns: {', '.join(missing)}")
            if extra:
                errors.append(f"review CSV has unexpected columns: {', '.join(extra)}")
            rows = list(reader)
    except OSError as exc:
        return (f"cannot read review CSV: {exc}",)

    seen: set[str] = set()
    for line_number, row in enumerate(rows, start=2):
        clip_id = row.get("clip_id", "").strip()
        prefix = f"line {line_number}"
        if clip_id not in clips:
            errors.append(f"{prefix}: unknown clip_id {clip_id!r}")
            continue
        if clip_id in seen:
            errors.append(f"{prefix}: duplicate clip_id {clip_id}")
        seen.add(clip_id)
        status = row.get("verification_status", "").strip()
        if status not in _VERIFICATION_STATES:
            errors.append(
                f"{prefix} {clip_id}: verification_status must be one of "
                "human_verified, partial, or unverified"
            )
        if status in {"human_verified", "partial"}:
            if not row.get("reviewer_id", "").strip():
                errors.append(f"{prefix} {clip_id}: reviewer_id is required")
            if row.get("guide_version", "").strip() != guide_version:
                errors.append(f"{prefix} {clip_id}: guide_version does not match the manifest")
        clip_type = "video" if clip_id.startswith("video_") else "audio"
        if clip_type == "video":
            _validate_video(row, clips[clip_id], errors)
        else:
            _validate_audio(row, clips[clip_id], errors)

    for clip_id in clips:
        if clip_id not in seen:
            errors.append(f"review CSV is missing clip row {clip_id}")
    return tuple(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    errors = validate_review_labels(args.labels, args.manifest)
    if errors:
        print("Invalid or incomplete F10 review labels:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("F10 blind-review labels are valid and tied to manifest source PTS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
