"""Compare fixed and iterated axis decisions against hand-labeled JSONL windows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        rows.append(value)
    return rows


def _prediction(row: dict[str, Any], key: str) -> str | None:
    claim = row.get(key)
    if not isinstance(claim, dict):
        return None
    candidate = claim.get("candidate_id")
    return (
        candidate
        if claim.get("decision") == "accepted" and isinstance(candidate, str)
        else None
    )


def _ranked_candidate(row: dict[str, Any], key: str) -> str | None:
    claim = row.get(key)
    if not isinstance(claim, dict):
        return None
    candidate = claim.get("candidate_id")
    return candidate if isinstance(candidate, str) else None


def _score(
    predictions: list[str | None],
    ranked_candidates: list[str | None],
    expected: list[str],
) -> dict[str, object]:
    accepted = [prediction for prediction in predictions if prediction is not None]
    correct = sum(
        prediction == target
        for prediction, target in zip(predictions, expected, strict=True)
    )
    accepted_correct = sum(
        prediction == target
        for prediction, target in zip(predictions, expected, strict=True)
        if prediction is not None
    )
    ranked_correct = sum(
        candidate == target
        for candidate, target in zip(ranked_candidates, expected, strict=True)
    )
    return {
        "accuracy_all": correct / len(expected) if expected else None,
        "ranked_accuracy_all": ranked_correct / len(expected) if expected else None,
        "coverage": len(accepted) / len(expected) if expected else None,
        "accuracy_when_accepted": (
            accepted_correct / len(accepted) if accepted else None
        ),
        "accepted_count": len(accepted),
        "correct_count": correct,
        "ranked_correct_count": ranked_correct,
    }


def evaluate(
    iteration_rows: list[dict[str, Any]], label_rows: list[dict[str, Any]]
) -> dict[str, object]:
    window_labels: dict[tuple[str, str], str] = {}
    interval_labels: dict[tuple[str, str, int, int], str] = {}
    for row in label_rows:
        window_id = row.get("window_id")
        axis_id = row.get("axis_id")
        expected = row.get("expected_candidate_id")
        if not isinstance(axis_id, str) or not axis_id:
            raise ValueError("labels require a non-empty axis_id")
        if not isinstance(expected, str) or not expected:
            raise ValueError("labels require a non-empty expected_candidate_id")
        if isinstance(window_id, str) and window_id:
            key = (window_id, axis_id)
            if key in window_labels:
                raise ValueError(f"duplicate label for axis/window {key}")
            window_labels[key] = expected
            continue

        stream_id = row.get("stream_id")
        start_ms = row.get("start_ms")
        end_ms = row.get("end_ms")
        if (
            not isinstance(stream_id, str)
            or not stream_id
            or isinstance(start_ms, bool)
            or not isinstance(start_ms, int)
            or isinstance(end_ms, bool)
            or not isinstance(end_ms, int)
            or start_ms < 0
            or end_ms <= start_ms
        ):
            raise ValueError(
                "labels require window_id or stream_id/start_ms/end_ms, plus axis and expected"
            )
        interval_key = (stream_id, axis_id, start_ms, end_ms)
        if interval_key in interval_labels:
            raise ValueError(f"duplicate label for stream interval {interval_key}")
        interval_labels[interval_key] = expected

    paired: list[tuple[dict[str, Any], str]] = []
    for row in iteration_rows:
        if row.get("record_type") != "hypothesis_iteration":
            continue
        window_id = row.get("window_id")
        axis_id = row.get("axis_id")
        expected = None
        if isinstance(window_id, str) and isinstance(axis_id, str):
            expected = window_labels.get((window_id, axis_id))
        stream_id = row.get("stream_id")
        start_ms = row.get("start_ms")
        end_ms = row.get("end_ms")
        if (
            expected is None
            and isinstance(stream_id, str)
            and isinstance(axis_id, str)
            and isinstance(start_ms, int)
            and not isinstance(start_ms, bool)
            and isinstance(end_ms, int)
            and not isinstance(end_ms, bool)
        ):
            expected = interval_labels.get((stream_id, axis_id, start_ms, end_ms))
        if expected is not None:
            paired.append((row, expected))

    baseline_predictions = [_prediction(row, "baseline") for row, _ in paired]
    iterated_predictions = [_prediction(row, "iterated") for row, _ in paired]
    baseline_ranked_candidates = [_ranked_candidate(row, "baseline") for row, _ in paired]
    iterated_ranked_candidates = [_ranked_candidate(row, "iterated") for row, _ in paired]
    expected = [target for _, target in paired]
    attempt_statuses = {
        "rescored",
        "no_candidates",
        "no_distinct_candidates",
        "proposal_failed",
        "cpu_budget_exceeded",
    }
    attempts = [row for row, _ in paired if row.get("status") in attempt_statuses]
    return {
        "schema_version": 1,
        "matched_windows": len(paired),
        "label_windows": len(window_labels) + len(interval_labels),
        "unmatched_label_windows": len(window_labels) + len(interval_labels) - len(paired),
        "baseline": _score(baseline_predictions, baseline_ranked_candidates, expected),
        "iterated": _score(iterated_predictions, iterated_ranked_candidates, expected),
        "proposal_attempts": len(attempts),
        "proposal_latency_ms": round(
            sum(float(row.get("proposal_latency_ms", 0.0)) for row in attempts), 3
        ),
        "embedding_latency_ms": round(
            sum(float(row.get("embedding_latency_ms", 0.0)) for row in attempts), 3
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iterations", type=Path, help="JSONL from shsd analyze --iterative-axis")
    parser.add_argument("labels", type=Path, help="JSONL with manually reviewed expected labels")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = evaluate(_read_jsonl(args.iterations), _read_jsonl(args.labels))
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        print(serialized, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
