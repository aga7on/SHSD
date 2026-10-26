from __future__ import annotations

import json

import pytest

from shsd.memory import GroundedEventGraph, TimelineClaim, TimelineEvent


def _claim(claim_id: str, *, decision: str = "accepted") -> TimelineClaim:
    return TimelineClaim(
        claim_id=claim_id,
        label=claim_id,
        text_ru=f"Проверяемый факт: {claim_id}.",
        decision=decision,
        raw_cosine=0.81,
        margin=0.12,
        evidence_refs=(f"audio:{claim_id}:0-1000",),
        window_ids=(f"window:{claim_id}",),
        model_revision="model-rev-test",
        sample_count=1,
    )


def _event(
    event_id: str,
    start_ms: int,
    end_ms: int,
    claims: tuple[TimelineClaim, ...],
    *,
    revision: int = 1,
    level: str = "L2",
) -> TimelineEvent:
    return TimelineEvent(
        stream_id="source-1",
        epoch=0,
        event_id=event_id,
        revision=revision,
        start_ms=start_ms,
        end_ms=end_ms,
        kind="audio_scene_changed",
        level=level,
        state="committed",
        modality_mask={"audio": True, "video": False, "speech": False},
        claims=claims,
        supersedes_revision=revision - 1 if revision > 1 else None,
    )


def test_graph_keeps_latest_revisions_and_orders_without_claiming_causality() -> None:
    graph = GroundedEventGraph.from_events(
        [
            _event("event-a", 0, 5_000, (_claim("old",),), revision=1),
            _event("event-b", 3_000, 6_000, (_claim("next",),)),
            _event("event-a", 0, 5_000, (_claim("current",),), revision=2),
        ],
        stream_id="source-1",
        epoch=0,
    )

    assert [(event.event_id, event.revision) for event in graph.events] == [
        ("event-a", 2),
        ("event-b", 1),
    ]
    assert len(graph.edges) == 1
    assert graph.edges[0].relation == "starts_before"
    assert graph.edges[0].intervals_overlap
    assert graph.edges[0].causality_claimed is False
    payload = graph.to_dict()
    assert payload["ordering"] == "adjacent_event_start_time"
    assert payload["nodes"][0]["claims"][0]["confidence_is_probability"] is False
    assert json.dumps(payload, ensure_ascii=False, allow_nan=False)


def test_b0_requests_include_only_accepted_grounded_claims() -> None:
    graph = GroundedEventGraph.from_events(
        [
            _event(
                "event-a",
                0,
                1_000,
                (
                    _claim("accepted-1"),
                    _claim("uncertain", decision="uncertain"),
                    _claim("accepted-2"),
                    _claim("accepted-3"),
                ),
            ),
            _event("event-b", 1_000, 2_000, (_claim("accepted-4"),)),
        ],
        stream_id="source-1",
        epoch=0,
    )

    requests = graph.narration_requests()

    assert [len(request.claims) for request in requests] == [3, 1]
    assert all("uncertain" not in claim.claim_id for r in requests for claim in r.claims)
    assert all(claim.evidence_refs for request in requests for claim in request.claims)
    assert requests[0].stream_id == "source-1"
    assert requests[0].epoch == 0


def test_graph_rejects_events_from_another_source_or_epoch() -> None:
    with pytest.raises(ValueError, match="different graph source or epoch"):
        GroundedEventGraph.from_events(
            [_event("event-a", 0, 1_000, (_claim("claim"),))],
            stream_id="another-source",
            epoch=0,
        )
