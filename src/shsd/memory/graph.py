"""Typed, source-grounded temporal graph for the training-free B0 narrator."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from shsd.memory.models import TimelineEvent

if TYPE_CHECKING:
    from shsd.bridge.features import AVFeatureBatch

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
class VisualSequenceEvidence:
    """PTS-preserving feature provenance; it does not assert a visual action."""

    sequence_id: str
    source_id: str
    epoch: int
    timeline_interval_ms: tuple[int, int]
    source_pts_offset_ms: int
    frame_pts_ms: tuple[int, ...]
    frame_token_shapes: tuple[tuple[int, int], ...]
    model_revision: str
    preprocess_versions: tuple[str, ...]

    def __post_init__(self) -> None:
        start_ms, end_ms = self.timeline_interval_ms
        if not self.sequence_id or not self.source_id or not self.model_revision:
            raise ValueError("visual feature evidence requires source, sequence, and model IDs")
        if self.epoch < 0 or start_ms < 0 or end_ms <= start_ms:
            raise ValueError("visual feature evidence has an invalid epoch or interval")
        if self.source_pts_offset_ms < 0 or not self.frame_pts_ms:
            raise ValueError("visual feature evidence requires non-negative offset and frame PTS")
        if len(self.frame_pts_ms) != len(self.frame_token_shapes):
            raise ValueError("each visual frame PTS must have one token shape")
        if len(self.frame_pts_ms) != len(self.preprocess_versions):
            raise ValueError("each visual frame PTS must have one preprocessing version")
        if any(not start_ms <= pts_ms < end_ms for pts_ms in self.frame_pts_ms):
            raise ValueError("visual frame PTS must fall within the timeline interval")
        if any(
            left >= right
            for left, right in zip(self.frame_pts_ms, self.frame_pts_ms[1:], strict=False)
        ):
            raise ValueError("visual frame PTS must be strictly increasing")
        if any(
            len(shape) != 2 or any(size < 1 for size in shape) for shape in self.frame_token_shapes
        ):
            raise ValueError("visual token shapes must be non-empty [tokens, features] pairs")
        if not self.preprocess_versions or any(not version for version in self.preprocess_versions):
            raise ValueError("visual preprocessing provenance is required")

    @classmethod
    def from_feature_batch(
        cls,
        batch: AVFeatureBatch,
        *,
        source_pts_offset_ms: int = 0,
    ) -> VisualSequenceEvidence:
        if not batch.frames:
            raise ValueError("visual feature evidence requires at least one frame")
        if source_pts_offset_ms < 0:
            raise ValueError("source_pts_offset_ms must be non-negative")
        digest = hashlib.sha256(
            "\0".join(
                (
                    batch.source_id,
                    str(batch.epoch),
                    str(batch.start_ms),
                    str(batch.end_ms),
                    ",".join(str(frame.pts_ms) for frame in batch.frames),
                    batch.frames[0].tokens.model_revision,
                )
            ).encode("utf-8")
        ).hexdigest()[:24]
        return cls(
            sequence_id=digest,
            source_id=batch.source_id,
            epoch=batch.epoch,
            timeline_interval_ms=(batch.start_ms, batch.end_ms),
            source_pts_offset_ms=source_pts_offset_ms,
            frame_pts_ms=tuple(frame.pts_ms for frame in batch.frames),
            frame_token_shapes=tuple(
                tuple(int(size) for size in frame.tokens.embeddings.shape) for frame in batch.frames
            ),
            model_revision=batch.frames[0].tokens.model_revision,
            preprocess_versions=tuple(frame.tokens.preprocess_version for frame in batch.frames),
        )

    def to_dict(self) -> dict[str, Any]:
        start_ms, end_ms = self.timeline_interval_ms
        return {
            "sequence_id": self.sequence_id,
            "source_id": self.source_id,
            "epoch": self.epoch,
            "timeline_interval_ms": [start_ms, end_ms],
            "source_interval_ms": [
                start_ms + self.source_pts_offset_ms,
                end_ms + self.source_pts_offset_ms,
            ],
            "source_pts_offset_ms": self.source_pts_offset_ms,
            "evidence_status": "encoder_features_only",
            "semantic_action_inferred": False,
            "model_revision": self.model_revision,
            "frames": [
                {
                    "evidence_ref": (
                        f"visual-frame:{self.source_id}:{self.epoch}:"
                        f"{pts_ms + self.source_pts_offset_ms}"
                    ),
                    "timeline_pts_ms": pts_ms,
                    "source_pts_ms": pts_ms + self.source_pts_offset_ms,
                    "token_shape": list(shape),
                    "preprocess_version": version,
                }
                for pts_ms, shape, version in zip(
                    self.frame_pts_ms,
                    self.frame_token_shapes,
                    self.preprocess_versions,
                    strict=True,
                )
            ],
        }


@dataclass(frozen=True, slots=True)
class GroundedEventGraph:
    """Latest timeline revisions plus explicit start-order links for a single source."""

    stream_id: str
    epoch: int
    events: tuple[TimelineEvent, ...]
    edges: tuple[TemporalGraphEdge, ...]
    visual_sequences: tuple[VisualSequenceEvidence, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.stream_id or self.epoch < 0 or self.schema_version != 1:
            raise ValueError("graph requires a source, non-negative epoch, and schema v1")
        if any(
            event.stream_id != self.stream_id or event.epoch != self.epoch for event in self.events
        ):
            raise ValueError("all graph events must belong to the graph source and epoch")
        if len(self.edges) != max(0, len(self.events) - 1):
            raise ValueError("graph must contain one start-order edge per adjacent event pair")
        if any(
            sequence.source_id != self.stream_id or sequence.epoch != self.epoch
            for sequence in self.visual_sequences
        ):
            raise ValueError("visual feature evidence belongs to a different graph source or epoch")
        if len({item.sequence_id for item in self.visual_sequences}) != len(self.visual_sequences):
            raise ValueError("visual feature sequence IDs must be unique")

    @classmethod
    def from_events(
        cls,
        events: list[TimelineEvent] | tuple[TimelineEvent, ...],
        *,
        stream_id: str,
        epoch: int,
        visual_feature_batches: tuple[AVFeatureBatch, ...] = (),
        source_pts_offset_ms: int = 0,
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
        visual_sequences = tuple(
            VisualSequenceEvidence.from_feature_batch(
                batch,
                source_pts_offset_ms=source_pts_offset_ms,
            )
            for batch in visual_feature_batches
        )
        return cls(stream_id, epoch, ordered, edges, visual_sequences)

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
            "visual_sequences": [item.to_dict() for item in self.visual_sequences],
            "limitations": [
                (
                    "This graph contains emitted timeline claims only; it does not infer "
                    "visual entities or actions."
                ),
                "Visual token features preserve frame PTS but are not semantic action labels.",
                "Cosine similarity is not probability or human verification.",
                "Start-time ordering and interval overlap do not imply causality.",
            ],
        }

    def _node_dict(self, event: TimelineEvent) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "revision": event.revision,
            "interval_ms": [event.start_ms, event.end_ms],
            "kind": event.kind,
            "level": event.level,
            "state": event.state,
            "modality_mask": dict(event.modality_mask),
            "visual_evidence_refs": [
                frame["evidence_ref"]
                for sequence in self.visual_sequences
                if event.start_ms < sequence.timeline_interval_ms[1]
                and event.end_ms > sequence.timeline_interval_ms[0]
                for frame in sequence.to_dict()["frames"]
                if isinstance(frame, dict)
                and event.start_ms <= frame["timeline_pts_ms"] < event.end_ms
            ],
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
                (event, claim) for claim in claims if claim.decision == "accepted" and claim.text_ru
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
