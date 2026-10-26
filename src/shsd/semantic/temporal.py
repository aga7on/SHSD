"""Bounded neighboring-audio evidence and conservative L2 re-scoring."""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from numpy.typing import NDArray

from shsd.embeddings.cache import normalize_embedding
from shsd.memory.models import TimelineEvent
from shsd.semantic.hypotheses import HypothesisAxis
from shsd.semantic.matcher import MatchPolicy, SemanticClaim, SemanticMatcher


@dataclass(frozen=True, slots=True)
class AudioEmbeddingWindow:
    """One normalized audio embedding with its source-time interval."""

    start_ms: int
    end_ms: int
    window_id: str
    model_revision: str
    embedding: NDArray[np.float32]

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("audio embedding interval must satisfy 0 <= start < end")
        if not self.window_id or not self.model_revision:
            raise ValueError("audio embedding window id and model revision are required")
        if self.embedding.ndim != 1 or not np.isfinite(self.embedding).all():
            raise ValueError("audio embedding must be a finite one-dimensional vector")


@dataclass(frozen=True, slots=True)
class _WindowMatch:
    window: AudioEmbeddingWindow
    within_event: bool
    match: SemanticClaim
    target_decision: str
    target_score: float | None
    target_margin: float | None


class BoundedAudioEmbeddingHistory:
    """Keep a small, thread-safe source-time index for adjacent L2 checks."""

    def __init__(self, *, capacity: int = 256) -> None:
        if capacity < 2:
            raise ValueError("audio embedding history capacity must be at least two")
        self.capacity = capacity
        self._windows: OrderedDict[str, AudioEmbeddingWindow] = OrderedDict()
        self._lock = threading.RLock()

    def add(
        self,
        *,
        start_ms: int,
        end_ms: int,
        window_id: str,
        model_revision: str,
        embedding: np.ndarray,
    ) -> None:
        vector = normalize_embedding(np.asarray(embedding, dtype=np.float32).reshape(-1)).copy()
        vector.setflags(write=False)
        item = AudioEmbeddingWindow(
            start_ms=start_ms,
            end_ms=end_ms,
            window_id=window_id,
            model_revision=model_revision,
            embedding=vector,
        )
        with self._lock:
            self._windows.pop(window_id, None)
            self._windows[window_id] = item
            while len(self._windows) > self.capacity:
                self._windows.popitem(last=False)

    def context(
        self,
        *,
        start_ms: int,
        end_ms: int,
        model_revision: str,
        padding_ms: int,
        max_windows: int = 8,
    ) -> tuple[AudioEmbeddingWindow, ...]:
        """Return event-overlapping windows and the nearest before/after neighbors."""
        if start_ms < 0 or end_ms <= start_ms or padding_ms < 0 or max_windows < 2:
            raise ValueError("invalid audio context range or limit")
        with self._lock:
            available = [
                item
                for item in self._windows.values()
                if item.model_revision == model_revision
                and item.start_ms < end_ms + padding_ms
                and item.end_ms > max(0, start_ms - padding_ms)
            ]
        available.sort(key=lambda item: (item.start_ms, item.end_ms, item.window_id))
        inside = [
            item for item in available if item.start_ms < end_ms and item.end_ms > start_ms
        ]
        if len(inside) > max_windows:
            indices = np.linspace(0, len(inside) - 1, num=max_windows, dtype=int)
            inside = [inside[int(index)] for index in dict.fromkeys(indices.tolist())]
        selected = {item.window_id: item for item in inside}
        outside = [item for item in available if item.window_id not in selected]
        before = [item for item in outside if item.end_ms <= start_ms]
        after = [item for item in outside if item.start_ms >= end_ms]
        neighbors: list[AudioEmbeddingWindow] = []
        if before:
            neighbors.append(max(before, key=lambda item: (item.end_ms, item.start_ms)))
        if after:
            neighbors.append(min(after, key=lambda item: (item.start_ms, item.end_ms)))
        for item in neighbors:
            if len(selected) >= max_windows:
                break
            selected[item.window_id] = item
        return tuple(sorted(selected.values(), key=lambda item: (item.start_ms, item.end_ms)))

    def __len__(self) -> int:
        with self._lock:
            return len(self._windows)


class TemporalAudioRefiner:
    """Recheck an audio event with the same matcher plus adjacent-window consensus.

    L2 keeps the L1 candidate unless its temporal audio support is confirmed by
    the existing similarity and margin policy. It never lowers either threshold.
    """

    def __init__(
        self,
        *,
        history: BoundedAudioEmbeddingHistory,
        axes: list[tuple[HypothesisAxis, dict[str, np.ndarray]]],
        matcher: SemanticMatcher,
        policy: MatchPolicy,
        context_padding_ms: int,
        max_context_windows: int = 8,
        minimum_support_windows: int = 2,
    ) -> None:
        if context_padding_ms < 0 or max_context_windows < 2 or minimum_support_windows < 2:
            raise ValueError("invalid temporal audio refinement settings")
        self.history = history
        self.axes = {axis.axis_id: (axis, vectors) for axis, vectors in axes}
        self.matcher = matcher
        self.policy = policy
        self.context_padding_ms = context_padding_ms
        self.max_context_windows = max_context_windows
        self.minimum_support_windows = minimum_support_windows

    def refine(self, event: TimelineEvent) -> tuple[TimelineEvent, dict[str, Any]]:
        """Return an L2-ready event revision and a diagnostic semantic record."""
        if not event.modality_mask.get("audio", False) or not event.claims:
            return event, self._skipped_report(event, "no_audio_claim")

        refined_claims = []
        claim_reports: list[dict[str, Any]] = []
        any_refined = False
        changed_to_uncertain = False
        for claim in event.claims:
            axis_id = next(
                (
                    reference.removeprefix("axis:")
                    for reference in claim.evidence_refs
                    if reference.startswith("axis:")
                ),
                None,
            )
            axis_data = self.axes.get(axis_id or "")
            if axis_data is None:
                refined_claims.append(claim)
                claim_reports.append(
                    {
                        "axis_id": axis_id,
                        "candidate_id": claim.label,
                        "status": "skipped",
                        "reason": "axis_reference_unavailable",
                    }
                )
                continue

            axis, candidate_vectors = axis_data
            if claim.label not in candidate_vectors:
                refined_claims.append(claim)
                claim_reports.append(
                    {
                        "axis_id": axis.axis_id,
                        "candidate_id": claim.label,
                        "status": "skipped",
                        "reason": "candidate_not_in_axis",
                    }
                )
                continue
            context = self.history.context(
                start_ms=event.start_ms,
                end_ms=event.end_ms,
                model_revision=claim.model_revision,
                padding_ms=self.context_padding_ms,
                max_windows=self.max_context_windows,
            )
            interior = [
                item
                for item in context
                if item.start_ms < event.end_ms and item.end_ms > event.start_ms
            ]
            if len(interior) < self.minimum_support_windows:
                refined_claims.append(claim)
                claim_reports.append(
                    {
                        "axis_id": axis.axis_id,
                        "candidate_id": claim.label,
                        "status": "skipped",
                        "reason": "insufficient_in_event_audio_windows",
                        "in_event_window_count": len(interior),
                        "required_window_count": self.minimum_support_windows,
                        "context_window_ids": [item.window_id for item in context],
                    }
                )
                continue

            interior_ids = {item.window_id for item in interior}
            window_matches = [
                self._match_window(
                    axis,
                    candidate_vectors,
                    item,
                    target_id=claim.label,
                    within_event=(item.window_id in interior_ids),
                )
                for item in context
            ]
            in_event_matches = [item for item in window_matches if item.within_event]
            target_votes = [
                item
                for item in in_event_matches
                if item.target_decision != "rejected"
            ]
            target_accepts = [
                item for item in in_event_matches if item.target_decision == "accepted"
            ]
            try:
                aggregate_vector = normalize_embedding(
                    np.mean(np.stack([item.embedding for item in interior]), axis=0)
                )
            except ValueError:
                refined_claims.append(claim)
                claim_reports.append(
                    {
                        "axis_id": axis.axis_id,
                        "candidate_id": claim.label,
                        "status": "skipped",
                        "reason": "aggregate_embedding_not_comparable",
                        "in_event_window_count": len(interior),
                        "context_window_ids": [item.window_id for item in context],
                    }
                )
                continue
            aggregate = self.matcher.match_axis(
                axis,
                aggregate_vector,
                candidate_vectors,
                policy=self.policy,
                model_revision=claim.model_revision,
                evidence_refs=tuple(
                    f"embedding:{item.window_id}" for item in interior
                ),
            )
            aggregate_decision, aggregate_score, aggregate_margin = self._target_result(
                aggregate, claim.label, mutually_exclusive=axis.mutually_exclusive
            )
            competing_consensus = False
            if axis.mutually_exclusive:
                candidate_counts: dict[str, int] = {}
                for item in in_event_matches:
                    if item.match.decision == "accepted":
                        candidate_counts[item.match.candidate_id] = (
                            candidate_counts.get(item.match.candidate_id, 0) + 1
                        )
                competing_consensus = any(
                    candidate_id != claim.label
                    and count >= self.minimum_support_windows
                    for candidate_id, count in candidate_counts.items()
                )
            confirmed = (
                aggregate_decision == "accepted"
                and len(target_votes) >= self.minimum_support_windows
                and not competing_consensus
            )
            decision = "accepted" if confirmed else "uncertain"
            context_refs = tuple(
                dict.fromkeys(
                    [
                        *claim.evidence_refs,
                        *(f"embedding:{item.window.window_id}" for item in window_matches),
                        f"l2:temporal-audio:{event.start_ms}-{event.end_ms}",
                    ]
                )
            )
            support_ids = tuple(dict.fromkeys(item.window.window_id for item in target_votes))
            updated_claim = replace(
                claim,
                decision=decision,
                raw_cosine=(
                    aggregate_score
                    if confirmed and aggregate_score is not None
                    else claim.raw_cosine
                ),
                margin=(
                    aggregate_margin
                    if confirmed and aggregate_margin is not None
                    else claim.margin
                ),
                evidence_refs=context_refs,
                window_ids=tuple(dict.fromkeys((*claim.window_ids, *support_ids))),
                sample_count=max(claim.sample_count, len(target_votes)),
            )
            refined_claims.append(updated_claim)
            any_refined = True
            changed_to_uncertain = changed_to_uncertain or (
                claim.decision == "accepted" and decision != "accepted"
            )
            claim_reports.append(
                {
                    "axis_id": axis.axis_id,
                    "candidate_id": claim.label,
                    "status": "confirmed" if confirmed else "abstained",
                    "reason": (
                        None
                        if confirmed
                        else "competing_candidate_consensus"
                        if competing_consensus
                        else "aggregate_or_window_support_below_policy"
                    ),
                    "thresholds": {
                        "minimum_similarity": self.policy.minimum_similarity,
                        "minimum_margin": self.policy.minimum_margin,
                        "minimum_support_windows": self.minimum_support_windows,
                        "similarity_is_probability": False,
                    },
                    "aggregate": {
                        "candidate_id": aggregate.candidate_id,
                        "decision": aggregate_decision,
                        "raw_cosine": aggregate_score,
                        "margin": aggregate_margin,
                    },
                    "support": {
                        "in_event_windows": len(in_event_matches),
                        "target_votes": len(target_votes),
                        "target_accepted": len(target_accepts),
                        "context_window_ids": [item.window.window_id for item in window_matches],
                        "target_window_ids": list(support_ids),
                    },
                    "windows": [self._window_payload(item, claim.label) for item in window_matches],
                    "temporal_context": self._neighbor_summary(window_matches, claim.label),
                }
            )

        if not any_refined:
            return event, {
                "record_type": "l2_refinement",
                "event_id": event.event_id,
                "source_revision": event.revision,
                "strategy": "neighbor_embedding_consensus_v1",
                "status": "skipped",
                "claims": claim_reports,
            }
        refined_event = replace(
            event,
            claims=tuple(refined_claims),
            kind="unknown" if changed_to_uncertain else event.kind,
        )
        statuses = {item["status"] for item in claim_reports}
        return refined_event, {
            "record_type": "l2_refinement",
            "event_id": event.event_id,
            "source_revision": event.revision,
            "strategy": "neighbor_embedding_consensus_v1",
            "status": "confirmed" if "confirmed" in statuses else "abstained",
            "claims": claim_reports,
        }

    def _match_window(
        self,
        axis: HypothesisAxis,
        candidate_vectors: dict[str, np.ndarray],
        window: AudioEmbeddingWindow,
        *,
        target_id: str,
        within_event: bool,
    ) -> _WindowMatch:
        match = self.matcher.match_axis(
            axis,
            window.embedding,
            candidate_vectors,
            policy=self.policy,
            model_revision=window.model_revision,
            evidence_refs=(f"audio:{window.start_ms}-{window.end_ms}",),
        )
        target_decision, target_score, target_margin = self._target_result(
            match, target_id, mutually_exclusive=axis.mutually_exclusive
        )
        return _WindowMatch(
            window=window,
            within_event=within_event,
            match=match,
            target_decision=target_decision,
            target_score=target_score,
            target_margin=target_margin,
        )

    def _target_result(
        self,
        match: SemanticClaim,
        target_id: str,
        *,
        mutually_exclusive: bool,
    ) -> tuple[str, float | None, float | None]:
        for candidate in (*match.supported_candidates, *match.top_candidates):
            if candidate.candidate_id == target_id:
                margin = (
                    max(0.0, candidate.raw_cosine - self.policy.minimum_similarity)
                    if not mutually_exclusive
                    else max(
                        0.0,
                        candidate.raw_cosine
                        - max(
                            (
                                other.raw_cosine
                                for other in match.top_candidates
                                if other.candidate_id != target_id
                            ),
                            default=-1.0,
                        ),
                    )
                )
                return candidate.decision, candidate.raw_cosine, margin
        return "rejected", None, None

    @staticmethod
    def _window_payload(item: _WindowMatch, target_id: str) -> dict[str, Any]:
        return {
            "window_id": item.window.window_id,
            "start_ms": item.window.start_ms,
            "end_ms": item.window.end_ms,
            "relation": "inside_event" if item.within_event else "adjacent",
            "candidate_id": item.match.candidate_id,
            "decision": item.match.decision,
            "raw_cosine": item.match.raw_cosine,
            "margin": item.match.margin,
            "target_candidate_id": target_id,
            "target_decision": item.target_decision,
            "target_raw_cosine": item.target_score,
            "target_margin": item.target_margin,
        }

    @staticmethod
    def _neighbor_summary(items: list[_WindowMatch], target_id: str) -> dict[str, Any]:
        before = [item for item in items if item.window.end_ms <= min(
            (other.window.start_ms for other in items if other.within_event), default=0
        )]
        after = [item for item in items if item.window.start_ms >= max(
            (other.window.end_ms for other in items if other.within_event), default=0
        )]
        return {
            "target_candidate_id": target_id,
            "before_candidate_id": before[-1].match.candidate_id if before else None,
            "after_candidate_id": after[0].match.candidate_id if after else None,
            "before_decision": before[-1].match.decision if before else None,
            "after_decision": after[0].match.decision if after else None,
        }

    @staticmethod
    def _skipped_report(event: TimelineEvent, reason: str) -> dict[str, Any]:
        return {
            "record_type": "l2_refinement",
            "event_id": event.event_id,
            "source_revision": event.revision,
            "strategy": "neighbor_embedding_consensus_v1",
            "status": "skipped",
            "reason": reason,
            "claims": [],
        }
