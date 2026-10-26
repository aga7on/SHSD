"""Map listening-review CSV labels to interval JSONL for the A/B evaluator."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

ALLOWED_LABELS = {"speech_present", "speech_absent", "uncertain"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def convert(review_path: Path, key_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    review_rows = _read_csv(review_path)
    key_rows = _read_csv(key_path)
    key_by_id = {row.get("clip_id", ""): row for row in key_rows}
    if not key_by_id or "" in key_by_id or len(key_by_id) != len(key_rows):
        raise ValueError("answer key must contain unique non-empty clip_id values")

    labels_by_id: dict[str, str] = {}
    for row in review_rows:
        clip_id = row.get("clip_id", "").strip()
        label = row.get("label", "").strip()
        if clip_id not in key_by_id:
            raise ValueError(f"unknown clip_id in review CSV: {clip_id!r}")
        if clip_id in labels_by_id:
            raise ValueError(f"duplicate review row for clip_id: {clip_id}")
        if label not in ALLOWED_LABELS:
            raise ValueError(f"invalid label for {clip_id}: {label!r}")
        labels_by_id[clip_id] = label

    missing = sorted(set(key_by_id) - set(labels_by_id))
    if missing:
        raise ValueError(f"review CSV is missing {len(missing)} clip(s): {', '.join(missing[:5])}")

    output_rows: list[dict[str, Any]] = []
    counts = {label: 0 for label in sorted(ALLOWED_LABELS)}
    for clip_id, label in labels_by_id.items():
        counts[label] += 1
        if label == "uncertain":
            continue
        key = key_by_id[clip_id]
        output_rows.append(
            {
                "axis_id": key["axis_id"],
                "clip_id": clip_id,
                "end_ms": int(key["end_ms"]),
                "expected_candidate_id": label,
                "label_source": "independent_listening_review",
                "start_ms": int(key["start_ms"]),
                "stream_id": key["stream_id"],
            }
        )
    if not output_rows:
        raise ValueError("no binary labels to score; all clips were marked uncertain")
    return output_rows, {
        "schema_version": 1,
        "label_source": "independent_listening_review",
        "clips_reviewed": len(labels_by_id),
        "clips_scored": len(output_rows),
        "counts": counts,
        "uncertain_clip_ids": sorted(
            clip_id for clip_id, label in labels_by_id.items() if label == "uncertain"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_csv", type=Path, help="CSV exported by the local review player")
    parser.add_argument("answer_key_csv", type=Path, help="separate review pack answer key")
    parser.add_argument("--output", type=Path, required=True, help="interval label JSONL")
    parser.add_argument("--summary", type=Path, default=None, help="review count JSON")
    args = parser.parse_args()
    rows, summary = convert(args.review_csv, args.answer_key_csv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    summary_path = args.summary or args.output.with_suffix(".summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
