"""Deterministic exports from the persisted SHSD event journal."""

from __future__ import annotations

import json
from typing import Any, Literal

ExportFormat = Literal["json", "jsonl", "markdown"]


def _watermark_snapshot(record: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    nested = record.get("watermarks")
    return nested if isinstance(nested, dict) else {}


def export_warnings(
    events: list[dict[str, Any]],
    watermarks: dict[str, Any] | None,
    speech_segments: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    snapshot = _watermark_snapshot(watermarks)
    issues = snapshot.get("issues", [])
    if isinstance(issues, list):
        for issue in issues:
            if not isinstance(issue, dict) or issue.get("status") not in {
                "gap", "unavailable", "dropped", "failed", "skipped"
            }:
                continue
            warnings.append({"record_type": "warning", "kind": "coverage", **issue})
    for event in events:
        claims = event.get("claims", [])
        if not isinstance(claims, list):
            continue
        for claim in claims:
            if not isinstance(claim, dict) or claim.get("decision") not in {
                "uncertain", "unknown", "unverified"
            }:
                continue
            warnings.append(
                {
                    "record_type": "warning",
                    "kind": "uncertain_claim",
                    "event_id": event.get("event_id"),
                    "revision": event.get("revision"),
                    "claim_id": claim.get("claim_id"),
                    "decision": claim.get("decision"),
                    "label": claim.get("label"),
                    "text_ru": claim.get("text_ru"),
                    "start_ms": event.get("start_ms"),
                    "end_ms": event.get("end_ms"),
                }
            )
    for segment in speech_segments or []:
        if segment.get("status") in {"failed", "dropped"}:
            warnings.append(
                {
                    "record_type": "warning",
                    "kind": "speech_asr",
                    "status": segment.get("status"),
                    "start_ms": segment.get("start_ms"),
                    "end_ms": segment.get("end_ms"),
                    "reason": segment.get("error"),
                    "segment_id": segment.get("segment_id"),
                }
            )
    warnings.sort(
        key=lambda item: (
            int(item.get("start_ms", 0) or 0),
            str(item.get("kind", "")),
            str(item.get("event_id", "")),
        )
    )
    return warnings


def build_export_payload(
    *,
    stream_id: str,
    epoch: int,
    source: str,
    status: str,
    events: list[dict[str, Any]],
    captions: list[dict[str, Any]],
    watermarks: dict[str, Any] | None,
    include_history: bool,
    speech_segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "record_type": "stream_export",
        "stream_id": stream_id,
        "epoch": epoch,
        "source": source,
        "status": status,
        "include_history": include_history,
        "events": events,
        "captions": captions,
        "speech_segments": speech_segments or [],
        "watermarks": watermarks,
        "warnings": export_warnings(events, watermarks, speech_segments),
    }


def render_jsonl(payload: dict[str, Any]) -> str:
    rows: list[dict[str, Any]] = [
        {
            "schema_version": payload["schema_version"],
            "record_type": "stream_export",
            "stream_id": payload["stream_id"],
            "epoch": payload["epoch"],
            "source": payload["source"],
            "status": payload["status"],
            "include_history": payload["include_history"],
        }
    ]
    rows.extend({"record_type": "event", **event} for event in payload["events"])
    rows.extend(payload["captions"])
    rows.extend(payload.get("speech_segments", []))
    rows.extend(payload["warnings"])
    if payload.get("watermarks") is not None:
        rows.append(payload["watermarks"])
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
        for row in rows
    )


def _format_time(value: object) -> str:
    milliseconds = max(0, value) if isinstance(value, int) and not isinstance(value, bool) else 0
    minutes, remainder = divmod(milliseconds, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{minutes:02d}:{seconds:02d}.{millis // 100}"


def _caption_range(caption: dict[str, Any]) -> tuple[int, int]:
    time_range = caption.get("time_range")
    if isinstance(time_range, dict):
        start = time_range.get("start_ms", 0)
        end = time_range.get("end_ms", 0)
    else:
        start = caption.get("start_ms", 0)
        end = caption.get("end_ms", 0)
    return (
        start if isinstance(start, int) and not isinstance(start, bool) else 0,
        end if isinstance(end, int) and not isinstance(end, bool) else 0,
    )


def render_markdown(payload: dict[str, Any]) -> str:
    source = str(payload.get("source", "")).replace("\r", " ").replace("\n", " ")
    captions = [item for item in payload.get("captions", []) if isinstance(item, dict)]
    caption_segments: list[tuple[int, int, str, list[str]]] = []
    for caption in captions:
        text = caption.get("caption_ru")
        if not isinstance(text, str) or not text.strip():
            continue
        start_ms, end_ms = _caption_range(caption)
        refs = caption.get("event_revisions", [])
        event_refs = [
            f"`{item.get('event_id')}@r{item.get('revision')}`"
            for item in refs
            if isinstance(item, dict)
        ] if isinstance(refs, list) else []
        caption_segments.append((start_ms, end_ms, text.strip(), event_refs))

    events = [item for item in payload.get("events", []) if isinstance(item, dict)]
    for event in events:
        text = event.get("caption_ru")
        if not isinstance(text, str) or not text.strip():
            continue
        start_ms = int(event.get("start_ms", 0))
        end_ms = int(event.get("end_ms", 0))
        if any(
            start_ms == start and end_ms == end and text.strip() == value
            for start, end, value, _ in caption_segments
        ):
            continue
        caption_segments.append(
            (
                start_ms,
                end_ms,
                text.strip(),
                [f"`{event.get('event_id')}@r{event.get('revision')}`"],
            )
        )
    caption_segments.sort(key=lambda item: (item[0], item[1], item[2]))

    lines = [
        f"# Транскрипт SHSD: {payload.get('stream_id', '')}",
        "",
        f"- Источник: `{source}`",
        f"- Epoch: {payload.get('epoch', 0)}",
        f"- Статус: {payload.get('status', 'unknown')}",
        "",
        "## Связный текст из сохранённых captions",
        "",
    ]
    if caption_segments:
        lines.extend(segment[2] for segment in caption_segments)
    else:
        lines.append("Сохранённых captions уровня L3 нет. Новый inference не запускался.")

    lines.extend(["", "## Captions по медиавремени", ""])
    if caption_segments:
        for start_ms, end_ms, text, refs in caption_segments:
            suffix = f" ({', '.join(refs)})" if refs else ""
            lines.append(f"- [{_format_time(start_ms)}–{_format_time(end_ms)}] {text}{suffix}")
    else:
        lines.append("- Сохранённых captions нет.")

    lines.extend(["", "## Предупреждения о неопределённости и покрытии", ""])
    speech_segments = [
        item for item in payload.get("speech_segments", []) if isinstance(item, dict)
    ]
    lines.extend(["", "## Распознанная речь", ""])
    usable_speech = [
        item for item in speech_segments
        if item.get("status") == "final" and isinstance(item.get("text"), str)
        and item["text"].strip()
    ]
    if usable_speech:
        for segment in usable_speech:
            lines.append(
                f"- [{_format_time(segment.get('start_ms'))}–"
                f"{_format_time(segment.get('end_ms'))}] {segment['text'].strip()}"
            )
    else:
        lines.append("- Распознанных финальных сегментов нет.")

    warnings = payload.get("warnings", [])
    if not warnings:
        lines.append("- Предупреждений нет.")
    else:
        for warning in warnings:
            kind = warning.get("kind")
            if kind == "coverage":
                start = _format_time(warning.get("start_ms"))
                end = _format_time(warning.get("end_ms"))
                lane = (
                    warning.get("modality")
                    or warning.get("level")
                    or warning.get("stage")
                    or "coverage"
                )
                detail = warning.get("reason") or warning.get("status") or "coverage issue"
                lines.append(f"- [{start}–{end}] {warning.get('status')} · {lane}: {detail}")
            else:
                start = _format_time(warning.get("start_ms"))
                end = _format_time(warning.get("end_ms"))
                description = (
                    warning.get("text_ru")
                    or warning.get("label")
                    or warning.get("claim_id")
                )
                lines.append(
                    f"- [{start}–{end}] {warning.get('decision')} claim: {description} "
                    f"(`{warning.get('event_id')}@r{warning.get('revision')}`)"
                )
    return "\n".join(lines).rstrip() + "\n"
