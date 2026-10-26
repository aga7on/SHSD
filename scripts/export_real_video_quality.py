"""Export readable event tables from a SHSD JSONL analysis timeline."""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMELINE = (
    ROOT / "benchmarks" / "reports" / "real_video_quality_20261026" / "timeline.jsonl"
)


def _load_records(path: Path) -> list[dict[str, Any]]:
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if any(not isinstance(record, dict) for record in records):
        raise ValueError("timeline rows must be JSON objects")
    return records


def _latest_level_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        if record.get("record_type") != "event" or record.get("level") not in {"L1", "L2"}:
            continue
        key = (str(record.get("event_id", "")), str(record["level"]))
        previous = latest.get(key)
        if previous is None or int(record.get("revision", 0)) > int(
            previous.get("revision", 0)
        ):
            latest[key] = record
    return sorted(
        latest.values(),
        key=lambda item: (
            int(item.get("start_ms", 0)),
            str(item.get("level", "")),
            str(item.get("event_id", "")),
        ),
    )


def _claim_description(claim: dict[str, Any]) -> str:
    label = str(claim.get("label") or claim.get("claim_id") or "claim")
    decision = str(claim.get("decision") or "unknown")
    text = claim.get("text_ru")
    if not isinstance(text, str) or not text.strip():
        return f"{label} [{decision}]"
    return f"{label} [{decision}]: {text.strip()}"


def _event_row(event: dict[str, Any]) -> dict[str, str]:
    claims = [claim for claim in event.get("claims", []) if isinstance(claim, dict)]
    descriptions = [_claim_description(claim) for claim in claims]
    return {
        "start_ms": str(event.get("start_ms", "")),
        "end_ms": str(event.get("end_ms", "")),
        "level": str(event.get("level", "")),
        "kind": str(event.get("kind", "")),
        "state": str(event.get("state", "")),
        "revision": str(event.get("revision", "")),
        "event_id": str(event.get("event_id", "")),
        "description_ru": " | ".join(descriptions),
        "claims_json": json.dumps(claims, ensure_ascii=False, sort_keys=True),
        "modality_mask": json.dumps(
            event.get("modality_mask", {}), ensure_ascii=False, sort_keys=True
        ),
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def _event_table(events: list[dict[str, Any]]) -> str:
    lines = [
        "| Source range | Level | State | Kind | Russian claim descriptions | Event/revision |",
        "|---|---|---|---|---|---|",
    ]
    for event in events:
        descriptions = "<br>".join(
            _cell(_claim_description(claim))
            for claim in event.get("claims", [])
            if isinstance(claim, dict)
        ) or "(no claim text)"
        lines.append(
            (
                "| {start}-{end} ms | {level} | {state} | {kind} | "
                "{descriptions} | {event_id} r{revision} |"
            ).format(
                start=event.get("start_ms", ""),
                end=event.get("end_ms", ""),
                level=event.get("level", ""),
                state=event.get("state", ""),
                kind=event.get("kind", ""),
                descriptions=descriptions,
                event_id=event.get("event_id", ""),
                revision=event.get("revision", ""),
            )
        )
    return "\n".join(lines)


def _caption_table(captions: list[dict[str, Any]]) -> str:
    lines = [
        "| Source range | Status | Russian caption | Cited event revisions |",
        "|---|---|---|---|",
    ]
    for caption in captions:
        interval = caption.get("time_range", {})
        start = interval.get("start_ms", caption.get("start_ms", ""))
        end = interval.get("end_ms", caption.get("end_ms", ""))
        refs = ", ".join(
            f"{item.get('event_id')} r{item.get('revision')}"
            for item in caption.get("event_revisions", [])
            if isinstance(item, dict)
        )
        lines.append(
            f"| {start}-{end} ms | {caption.get('status', '')} | "
            f"{_cell(caption.get('caption_ru', ''))} | {_cell(refs)} |"
        )
    return "\n".join(lines)


def _speech_table(segments: list[dict[str, Any]]) -> str:
    lines = ["| Source range | Status | Text | Error |", "|---|---|---|---|"]
    for segment in segments:
        lines.append(
            "| {start}-{end} ms | {status} | {text} | {error} |".format(
                start=segment.get("start_ms", ""),
                end=segment.get("end_ms", ""),
                status=segment.get("status", ""),
                text=_cell(segment.get("text", "")),
                error=_cell(segment.get("error", "")),
            )
        )
    return "\n".join(lines)


def _semantic_summary(matches: list[dict[str, Any]]) -> str:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for match in matches:
        grouped[(str(match.get("axis_id", "")), str(match.get("modality", "")))].append(
            match
        )
    lines = [
        (
            "| Axis | Modality | Windows | Decisions | "
            "Best cosine min/mean/max | Margin basis | "
            "Cosine below threshold | Margin below threshold | Margin min/mean/max |"
        ),
        "|---|---|---:|---|---|---|---:|---:|---|",
    ]
    for (axis, modality), rows in sorted(grouped.items()):
        scores = [float(row.get("raw_cosine", 0.0)) for row in rows]
        margins = [float(row.get("margin", 0.0)) for row in rows]
        policies = [
            row.get("thresholds")
            if isinstance(row.get("thresholds"), dict)
            else {}
            for row in rows
        ]
        minimum_similarities = [
            float(policy.get("minimum_similarity", 0.6)) for policy in policies
        ]
        minimum_margins = [float(policy.get("minimum_margin", 0.05)) for policy in policies]
        margin_bases = sorted(
            {str(policy.get("margin_basis", "unknown")) for policy in policies}
        )
        decisions = dict(Counter(str(row.get("decision", "")) for row in rows))
        below_similarity = sum(
            score < threshold
            for score, threshold in zip(scores, minimum_similarities, strict=True)
        )
        below_margin = sum(
            margin < threshold for margin, threshold in zip(margins, minimum_margins, strict=True)
        )
        score_stats = "/".join(
            f"{value:.3f}" for value in (min(scores), sum(scores) / len(scores), max(scores))
        )
        margin_stats = "/".join(
            f"{value:.3f}"
            for value in (
                min(margins),
                sum(margins) / len(margins),
                max(margins),
            )
        )
        lines.append(
            f"| {axis} | {modality} | {len(rows)} | {decisions} | "
            f"{score_stats} | {', '.join(margin_bases)} | {below_similarity} | "
            f"{below_margin} | {margin_stats} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", type=Path, default=DEFAULT_TIMELINE)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    timeline = args.timeline.resolve()
    if not timeline.is_file():
        parser.error(f"timeline does not exist: {timeline}")
    output_dir = (args.output_dir or timeline.parent).resolve()
    records = _load_records(timeline)
    analysis = next(
        (item for item in records if item.get("record_type") == "analysis"), {}
    )
    metrics = next(
        (item for item in records if item.get("record_type") == "metrics"), {}
    )
    events = _latest_level_events(records)
    captions = [item for item in records if item.get("record_type") == "caption"]
    segments = [item for item in records if item.get("record_type") == "speech_segment"]
    all_events = [item for item in records if item.get("record_type") == "event"]
    matches = [item for item in records if item.get("record_type") == "window_match"]

    event_rows = [_event_row(event) for event in events]
    caption_rows = [
        {
            "start_ms": str(item.get("time_range", {}).get("start_ms", "")),
            "end_ms": str(item.get("time_range", {}).get("end_ms", "")),
            "status": str(item.get("status", "")),
            "backend": str(item.get("backend", "")),
            "caption_ru": str(item.get("caption_ru", "")),
            "warnings": "; ".join(item.get("warnings", [])),
            "event_revisions": json.dumps(
                item.get("event_revisions", []), ensure_ascii=False, sort_keys=True
            ),
        }
        for item in captions
    ]
    speech_rows = [
        {
            "start_ms": str(item.get("start_ms", "")),
            "end_ms": str(item.get("end_ms", "")),
            "status": str(item.get("status", "")),
            "language": str(item.get("language", "")),
            "text": str(item.get("text", "")),
            "error": str(item.get("error", "")),
        }
        for item in segments
    ]
    _write_csv(output_dir / "events_l1_l2_latest.csv", event_rows)
    _write_csv(output_dir / "captions_l3.csv", caption_rows)
    _write_csv(output_dir / "speech_segments.csv", speech_rows)
    _write_csv(
        output_dir / "semantic_match_scores.csv",
        [
            {
                "start_ms": str(item.get("start_ms", "")),
                "end_ms": str(item.get("end_ms", "")),
                "modality": str(item.get("modality", "")),
                "axis_id": str(item.get("axis_id", "")),
                "candidate_id": str(item.get("candidate_id", "")),
                "decision": str(item.get("decision", "")),
                "raw_cosine": str(item.get("raw_cosine", "")),
                "margin": str(item.get("margin", "")),
                "minimum_similarity": str(
                    item.get("thresholds", {}).get("minimum_similarity", "")
                ),
                "minimum_margin": str(item.get("thresholds", {}).get("minimum_margin", "")),
                "margin_basis": str(item.get("thresholds", {}).get("margin_basis", "")),
                "text_ru": str(item.get("text_ru", "")),
                "top_candidates_json": json.dumps(
                    item.get("top_candidates", []), ensure_ascii=False, sort_keys=True
                ),
            }
            for item in matches
        ],
    )

    level_counts = Counter(item.get("level") for item in all_events)
    final_watermarks = metrics.get("final_watermarks", {})
    watermark_text = json.dumps(final_watermarks, ensure_ascii=False, sort_keys=True)
    caption_status = Counter(
        (str(item.get("status", "")), str(item.get("backend", "")))
        for item in captions
    )
    latest_speech_by_id: dict[str, dict[str, Any]] = {}
    for item in segments:
        segment_id = str(
            item.get(
                "segment_id",
                f"{item.get('start_ms', '')}:{item.get('end_ms', '')}",
            )
        )
        previous = latest_speech_by_id.get(segment_id)
        if previous is None or int(item.get("revision", 1)) >= int(
            previous.get("revision", 1)
        ):
            latest_speech_by_id[segment_id] = item
    latest_speech_segments = sorted(
        latest_speech_by_id.values(), key=lambda item: int(item.get("start_ms", 0))
    )
    speech_statuses = Counter(str(item.get("status", "")) for item in latest_speech_segments)
    speech_dropped = speech_statuses.get("dropped", 0)
    speech_transcribed = sum(
        item.get("status") in {"partial", "final"}
        and bool(str(item.get("text", "")).strip())
        for item in latest_speech_segments
    )
    issues = final_watermarks.get("issues", [])
    issue_counts = Counter(
        (item.get("stage"), item.get("level"), item.get("modality"), item.get("reason"))
        for item in issues
    )
    issue_lines = [
        f"- stage={stage}, level={level or '-'}, modality={modality or '-'}, "
        f"reason={reason}: {count} range(s)"
        for (stage, level, modality, reason), count in sorted(
            issue_counts.items(), key=lambda item: tuple(str(part) for part in item[0])
        )
    ]
    caption_examples = Counter(str(item.get("caption_ru", "")) for item in captions)
    common_caption = max(caption_examples, key=caption_examples.get) if caption_examples else ""
    elapsed = metrics.get("end_to_end_elapsed")
    duration = analysis.get("source_duration_ms")
    timeline_reference = Path(os.path.relpath(timeline, output_dir)).as_posix()
    report = (
        "# Real-video L1/L2/L3 output\n\n"
        "## Run\n\n"
        f"- Source: {analysis.get('source', timeline)}\n"
        f"- Duration: {duration} ms; CPU; {analysis.get('threads', '?')} threads; "
        f"{analysis.get('window_ms', '?')} ms windows; Qwen narrator.\n"
        f"- End-to-end elapsed: {elapsed} s. File-mode L2/L3 were produced after "
        "media collection completed.\n"
        f"- Event revisions in JSONL: {metrics.get('event_revision_count', 0)}; "
        f"window matches: {metrics.get('window_match_count', 0)}; "
        f"skipped matches: {metrics.get('skipped_match_count', 0)}.\n"
        f"- Event record counts across revisions: L0={level_counts.get('L0', 0)}, "
        f"L1={level_counts.get('L1', 0)}, L2={level_counts.get('L2', 0)}; "
        f"latest L1/L2 rows are listed below ({len(events)} rows).\n\n"
        "## Semantic matcher scores\n\n"
        "Cosines are scores, not probabilities. The table counts rows below the "
        "per-match similarity and margin thresholds; margin basis distinguishes "
        "top-candidate gap from distance above the similarity threshold. The CSV "
        "includes each row's exact policy and candidate ranking.\n\n"
        f"{_semantic_summary(matches)}\n\n"
        "## L1 and L2 events\n\n"
        "Descriptions below are the model's Russian claim text. The decision is kept "
        "beside each description; uncertain claims are not treated as verified facts.\n\n"
        f"{_event_table(events)}\n\n"
        "## L3 captions\n\n"
        f"Qwen status counts: {dict(caption_status)}. Most common caption "
        f"({caption_examples.get(common_caption, 0)} occurrences): {common_caption}\n\n"
        f"{_caption_table(captions)}\n\n"
        "## ASR and coverage\n\n"
        f"Unique speech windows: {len(latest_speech_segments)}; latest statuses: "
        f"{dict(speech_statuses)}; non-empty transcript text: "
        f"{speech_transcribed}/{len(latest_speech_segments)}; dropped: {speech_dropped}. "
        "speech_segments.csv retains every partial/final revision.\n\n"
        f"{_speech_table(latest_speech_segments)}\n\n"
        f"Final watermarks: {watermark_text}\n\n"
        "Coverage issues:\n\n"
        + ("\n".join(issue_lines) if issue_lines else "- none")
        + "\n\n## Reading the result\n\n"
        "The run produces Russian event and caption strings, but the captions are "
        "repetitive scene-change descriptions and do not describe dialogue, music "
        "development, or instruments. ASR returned non-empty text for "
        f"{speech_transcribed}/{len(latest_speech_segments)} unique windows; this is "
        "raw model output and transcript accuracy has not been independently rated. "
        "Uncertain semantic claims remain visible but are not verified facts. This is "
        "a quality assessment, not a positive accuracy result.\n"
        f"\nMachine-readable files: [{timeline_reference}]({timeline_reference}), "
        "semantic_match_scores.csv, events_l1_l2_latest.csv, captions_l3.csv, "
        "speech_segments.csv.\n"
    )
    (output_dir / "report_real_video_quality.md").write_text(
        report, encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "l1_l2_rows": len(events),
                "captions": len(captions),
                "speech_windows": len(latest_speech_segments),
                "speech_revisions": len(segments),
                "speech_transcribed": speech_transcribed,
                "speech_dropped": speech_dropped,
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
