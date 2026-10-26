"""Typed, source-grounded temporal graph for the training-free B0 narrator."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from shsd.memory.models import TimelineEvent

TemporalRelationKind = Literal["starts_before"]


@dataclass(frozen=True, slots=True)
class TemporalGraphEdge:
    """An ordering edge between adjacent event starts; it makes no causal claim."""

    source_event_id: str
    source_revision: int
    target_event_id: str
    target_revision: int
    relation: TemporalRelationKind
    intervals_overlap: bool
    evidence_refs: tuple[str, ...]
    causality_claimed: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": {"event_id": self.source_event_id, "revision": self.source_revision},
            "target": {"event_id": self.target_event_id, "revision": self.target_revision},
            "relation": self.relation,
            "intervals_overlap": self.intervals_overlap,
            "evidence_refs": list(self.evidence_refs),
            "causality_claimed": False,
        }


@dataclass(frozen=True, slots=True)
class GroundedEventGraph:
    """Latest timeline revisions plus explicit start-order links for a single source."""

    stream_id: str
    epoch: int
    events: tuple[TimelineEvent, ...]
    edges: tuple[TemporalGraphEdge, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.stream_id or self.epoch < 0 or self.schema_version != 1:
            raise ValueError("graph requires a source, non-negative epoch, and schema v1")
        if any(
            event.stream_id != self.stream_id or event.epoch != self.epoch
            for event in self.events
        ):
            raise ValueError("all graph events must belong to the graph source and epoch")
        if len(self.edges) != max(0, len(self.events) - 1):
            raise ValueError("graph must contain one start-order edge per adjacent event pair")

    @classmethod
    def from_events(
        cls,
        events: list[TimelineEvent] | tuple[TimelineEvent, ...],
        *,
        stream_id: str,
        epoch: int,
    ) -> GroundedEventGraph:
        """Keep the newest revision for each event and link nodes by start-time order."""
        latest: dict[str, TimelineEvent] = {}
        for event in events:
            if event.stream_id != stream_id or event.epoch != epoch:
                raise ValueError("input event belongs to a different graph source or epoch")
            prior = latest.get(event.event_id)
            if prior is None or event.revision > prior.revision:
                latest[event.event_id] = event
        ordered = tuple(
            sorted(
                latest.values(),
                key=lambda item: (item.start_ms, item.end_ms, item.event_id),
            )
        )
        edges = tuple(
            TemporalGraphEdge(
                source_event_id=left.event_id,
                source_revision=left.revision,
                target_event_id=right.event_id,
                target_revision=right.revision,
                relation="starts_before",
                intervals_overlap=right.start_ms < left.end_ms,
                evidence_refs=tuple(
                    dict.fromkeys(
                        ref
                        for event in (left, right)
                        for claim in event.claims
                        for ref in claim.evidence_refs
                    )
                ),
            )
            for left, right in zip(ordered, ordered[1:], strict=False)
        )
        return cls(stream_id, epoch, ordered, edges)

    def to_dict(self) -> dict[str, Any]:
        """Serialize graph evidence without translating hypotheses into verified facts."""
        return {
            "record_type": "event_graph",
            "schema_version": self.schema_version,
            "graph_id": hashlib.sha256(
                "\0".join(
                    [self.stream_id, str(self.epoch)]
                    + [f"{event.event_id}:{event.revision}" for event in self.events]
                ).encode("utf-8")
            ).hexdigest()[:24],
            "stream_id": self.stream_id,
            "epoch": self.epoch,
            "ordering": "adjacent_event_start_time",
            "nodes": [self._node_dict(event) for event in self.events],
            "edges": [edge.to_dict() for edge in self.edges],
            "limitations": [
                (
                    "This graph contains emitted timeline claims only; it does not infer "
                    "visual entities or actions."
                ),
                "Cosine similarity is not probability or human verification.",
                "Start-time ordering and interval overlap do not imply causality.",
            ],
        }

    @staticmethod
    def _node_dict(event: TimelineEvent) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "revision": event.revision,
            "interval_ms": [event.start_ms, event.end_ms],
            "kind": event.kind,
            "level": event.level,
            "state": event.state,
            "modality_mask": dict(event.modality_mask),
            "claims": [
                {
                    **claim.to_dict(),
                    "decision_state": (
                        "accepted_by_policy"
                        if claim.decision == "accepted"
                        else "hypothesis"
                        if claim.decision == "uncertain"
                        else claim.decision
                    ),
                    "confidence_kind": (
                        "cosine_similarity" if claim.raw_cosine is not None else "unavailable"
                    ),
                    "confidence_is_probability": False,
                }
                for claim in event.claims
            ],
        }

    def narration_requests(self) -> list[Any]:
        """Build the B0 graph→grounded-facts→Qwen inputs from accepted claims only."""
        from shsd.captions.narrator import NarrationClaim, NarrationEventRef, NarrationRequest

        sources: list[tuple[TimelineEvent, Any]] = []
        for event in self.events:
            claims = sorted(
                event.claims,
                key=lambda claim: (
                    claim.premise_state != "music_confirmed"
                    or claim.label
                    in {
                        "conversation_dominant",
                        "environment_dominant",
                        "music_absent",
                        "music_and_speech",
                        "music_present",
                    },
                    claim.label,
                    claim.claim_id,
                ),
            )
            sources.extend(
                (event, claim)
                for claim in claims
                if claim.decision == "accepted" and claim.text_ru
            )

        requests: list[NarrationRequest] = []
        for offset in range(0, len(sources), 3):
            refs_by_id: dict[str, NarrationEventRef] = {}
            claims: list[NarrationClaim] = []
            for event, claim in sources[offset : offset + 3]:
                refs_by_id[event.event_id] = NarrationEventRef(event.event_id, event.revision)
                claims.append(
                    NarrationClaim(
                        claim_id=f"{event.event_id}:{claim.claim_id}",
                        event_id=event.event_id,
                        revision=event.revision,
                        start_ms=event.start_ms,
                        end_ms=event.end_ms,
                        text_ru=claim.text_ru,
                        evidence_refs=claim.evidence_refs[:12],
                    )
                )
            requests.append(
                NarrationRequest(
                    stream_id=self.stream_id,
                    epoch=self.epoch,
                    event_refs=tuple(refs_by_id.values()),
                    claims=tuple(claims),
                )
            )
        return requests
