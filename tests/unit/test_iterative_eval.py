from __future__ import annotations

from scripts.evaluate_iterative_hypotheses import evaluate


def test_labeled_ab_report_compares_accuracy_coverage_and_single_proposal_latency() -> None:
    rows = [
        {
            "record_type": "hypothesis_iteration",
            "axis_id": "instrument_family",
            "window_id": "w1",
            "status": "rescored",
            "baseline": {"candidate_id": "synth", "decision": "accepted"},
            "iterated": {"candidate_id": "synth", "decision": "accepted"},
            "proposal_latency_ms": 100.0,
            "embedding_latency_ms": 50.0,
        },
        {
            "record_type": "hypothesis_iteration",
            "axis_id": "instrument_family",
            "window_id": "w2",
            "status": "reused",
            "baseline": {"candidate_id": "unknown", "decision": "uncertain"},
            "iterated": {"candidate_id": "synth", "decision": "accepted"},
            "proposal_latency_ms": 100.0,
            "embedding_latency_ms": 50.0,
        },
    ]
    labels = [
        {
            "axis_id": "instrument_family",
            "window_id": "w1",
            "expected_candidate_id": "synth",
        },
        {
            "axis_id": "instrument_family",
            "window_id": "w2",
            "expected_candidate_id": "synth",
        },
        {
            "axis_id": "instrument_family",
            "window_id": "w3",
            "expected_candidate_id": "synth",
        },
    ]

    report = evaluate(rows, labels)

    assert report["matched_windows"] == 2
    assert report["unmatched_label_windows"] == 1
    assert report["baseline"]["accuracy_all"] == 0.5  # type: ignore[index]
    assert report["baseline"]["ranked_accuracy_all"] == 0.5  # type: ignore[index]
    assert report["iterated"]["accuracy_all"] == 1.0  # type: ignore[index]
    assert report["iterated"]["ranked_accuracy_all"] == 1.0  # type: ignore[index]
    assert report["iterated"]["coverage"] == 1.0  # type: ignore[index]
    assert report["proposal_attempts"] == 1
    assert report["proposal_latency_ms"] == 100.0
    assert report["embedding_latency_ms"] == 50.0


def test_labeled_ab_report_can_join_stable_stream_intervals() -> None:
    rows = [
        {
            "record_type": "hypothesis_iteration",
            "axis_id": "speech_presence",
            "stream_id": "natural-speech",
            "start_ms": 0,
            "end_ms": 5000,
            "window_id": "model-specific-id",
            "baseline": {"candidate_id": "speech_present", "decision": "accepted"},
            "iterated": {"candidate_id": "speech_present", "decision": "accepted"},
            "status": "no_candidates",
            "proposal_latency_ms": 20.0,
        }
    ]
    labels = [
        {
            "axis_id": "speech_presence",
            "stream_id": "natural-speech",
            "start_ms": 0,
            "end_ms": 5000,
            "expected_candidate_id": "speech_present",
        }
    ]

    report = evaluate(rows, labels)

    assert report["matched_windows"] == 1
    assert report["unmatched_label_windows"] == 0
    assert report["baseline"]["accuracy_all"] == 1.0  # type: ignore[index]
    assert report["baseline"]["ranked_accuracy_all"] == 1.0  # type: ignore[index]
    assert report["iterated"]["accuracy_all"] == 1.0  # type: ignore[index]
