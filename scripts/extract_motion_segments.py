"""Post-process an SHSD analyze JSONL into motion segments and audio transitions.

This is a B0-style helper: it turns the existing frame_difference / audio
observations into bounded motion segments and acoustic transition intervals,
without claiming semantic actions or instruments.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _is_frame_difference(row: dict[str, Any]) -> bool:
    return (
        row.get("record_type") == "observation"
        and row.get("subtype") == "frame_difference"
    )


def _flush(
    current: list[dict[str, Any]], segments: list[dict[str, Any]]
) -> None:
    span = current[-1]["end_ms"] - current[0]["start_ms"]
    if span > 0:
        mean_diff = sum(float(r.get("value", 0.0)) for r in current) / len(current)
        segments.append(
            {
                "start_ms": current[0]["start_ms"],
                "end_ms": current[-1]["end_ms"],
                "mean_diff": round(mean_diff, 4),
                "frame_pairs": len(current),
            }
        )


def motion_segments_from_observations(
    rows: list[dict[str, Any]], threshold: float = 0.02
) -> list[dict[str, Any]]:
    diffs = [r for r in rows if _is_frame_difference(r)]
    diffs.sort(key=lambda r: (r["start_ms"], r["end_ms"]))
    segments: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for row in diffs:
        score = float(row.get("value", 0.0))
        if score >= threshold:
            current.append(row)
        elif current:
            _flush(current, segments)
            current = []
    if current:
        _flush(current, segments)
    return segments


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract motion segments from an SHSD analyze JSONL."
    )
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--threshold", type=float, default=0.02)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    rows = _read_jsonl(args.jsonl)
    segments = motion_segments_from_observations(rows, threshold=args.threshold)
    payload = {"motion_segments": segments, "count": len(segments)}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
