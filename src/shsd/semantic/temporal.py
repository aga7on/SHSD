"""Bounded neighboring-audio evidence and conservative L2 re-scoring."""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from numpy.typing import NDArray

from shsd.detectors.types import SignalObservation
from shsd.embeddings.cache import normalize_embedding
from shsd.memory.models import TimelineClaim, TimelineEvent
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
    signal_summary: tuple[tuple[str, float], ...] = ()
    signal_deltas: tuple[SignalObservation, ...] = ()

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
        signal_summary: Mapping[str, float | int] | None = None,
        signal_deltas: Sequence[SignalObservation] = (),
    ) -> None:
        vector = normalize_embedding(np.asarray(embedding, dtype=np.float32).reshape(-1)).copy()
        vector.setflags(write=False)
        item = AudioEmbeddingWindow(
            start_ms=start_ms,
            end_ms=end_ms,
            window_id=window_id,
            model_revision=model_revision,
            embedding=vector,
            signal_summary=tuple(
                sorted((key, float(value)) for key, value in (signal_summary or {}).items())
            ),
            signal_deltas=tuple(signal_deltas),
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
        detail_axes: Sequence[tuple[HypothesisAxis, dict[str, np.ndarray]]] = (),
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
        self.detail_axes = tuple(
            (axis, vectors) for axis, vectors in detail_axes if axis.level == "L2"
        )

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

        scene_claim = next(
            (
                claim
                for claim in refined_claims
                if any(
                    reference == "axis:music_presence" for reference in claim.evidence_refs
                )
            ),
            None,
        )
        premise_state = (
            _music_premise_state(
                scene_claim.label,
                scene_claim.decision,
                scene_claim.raw_cosine,
                scene_claim.candidate_hypotheses,
                minimum_similarity=self.policy.minimum_similarity,
            )
            if scene_claim is not None
            else "not_supported"
        )
        premise_claim_id = scene_claim.claim_id if scene_claim is not None else None
        premise_evidence_refs = scene_claim.evidence_refs if scene_claim is not None else ()
        if scene_claim is not None:
            updated_scene_claim = replace(
                scene_claim,
                premise_state=premise_state,
                premise_claim_id=scene_claim.claim_id,
                premise_evidence_refs=scene_claim.evidence_refs,
            )
            any_refined = any_refined or updated_scene_claim != scene_claim
            scene_claim = updated_scene_claim
            refined_claims = [
                scene_claim if claim.claim_id == scene_claim.claim_id else claim
                for claim in refined_claims
            ]
        new_details: list[TimelineClaim] = []
        detail_report: dict[str, Any] = {
            "detail_status": "skipped",
            "reason": "music_scene_not_confirmed",
            "music_premise": {
                "state": premise_state,
                "claim_id": premise_claim_id,
                "evidence_refs": list(premise_evidence_refs),
                "publication_allowed": premise_state == "music_confirmed",
            },
            "new_details": [],
            "static_details": [],
            "acoustic_changes": [],
            "signal_context": [],
            "neighbor_hypotheses": [],
            "candidate_changes": [],
        }
        if (
            scene_claim is not None
            and _music_scene_supports_details(
                scene_claim.label,
                scene_claim.decision,
                scene_claim.raw_cosine,
                scene_claim.candidate_hypotheses,
                minimum_similarity=self.policy.minimum_similarity,
            )
        ):
            new_details, detail_report = self._discover_music_details(
                event,
                scene_claim,
                publish_details=premise_state == "music_confirmed",
                premise_state=premise_state,
                premise_claim_id=scene_claim.claim_id,
                premise_evidence_refs=scene_claim.evidence_refs,
            )
            refined_claims.extend(new_details)
            any_refined = any_refined or bool(new_details)

        if not any_refined:
            return event, {
                "record_type": "l2_refinement",
                "event_id": event.event_id,
                "source_revision": event.revision,
                "strategy": "coarse_to_fine_temporal_audio_v2",
                "status": "skipped",
                "claims": claim_reports,
                **detail_report,
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
            "strategy": "coarse_to_fine_temporal_audio_v2",
            "status": "confirmed" if "confirmed" in statuses else "abstained",
            "claims": claim_reports,
            **detail_report,
        }

    def _discover_music_details(
        self,
        event: TimelineEvent,
        scene_claim: TimelineClaim,
        *,
        publish_details: bool,
        premise_state: str,
        premise_claim_id: str,
        premise_evidence_refs: tuple[str, ...],
    ) -> tuple[list[TimelineClaim], dict[str, Any]]:
        """Explore possible music internally; publish detail claims only on a confirmed premise."""
        context = self.history.context(
            start_ms=event.start_ms,
            end_ms=event.end_ms,
            model_revision=scene_claim.model_revision,
            padding_ms=self.context_padding_ms,
            max_windows=self.max_context_windows,
        )
        interior = [
            item
            for item in context
            if item.start_ms < event.end_ms and item.end_ms > event.start_ms
        ]
        signal_context = [
            {
                "window_id": item.window_id,
                "relation": (
                    "inside_event"
                    if item.start_ms < event.end_ms and item.end_ms > event.start_ms
                    else "adjacent"
                ),
                "metrics": dict(item.signal_summary),
            }
            for item in context
        ]
        acoustic_changes = [
            {
                "window_id": item.window_id,
                **observation.to_dict(),
            }
            for item in context
            for observation in item.signal_deltas
        ]
        if len(interior) < self.minimum_support_windows:
            return [], {
                "detail_status": "skipped",
                "reason": "insufficient_in_event_audio_windows",
                "music_premise": {
                    "state": premise_state,
                    "claim_id": premise_claim_id,
                    "evidence_refs": list(premise_evidence_refs),
                    "publication_allowed": publish_details,
                },
                "new_details": [],
                "static_details": [],
                "acoustic_changes": acoustic_changes,
                "signal_context": signal_context,
                "neighbor_hypotheses": [],
                "candidate_changes": [],
                "context_window_ids": [item.window_id for item in context],
            }

        try:
            aggregate_vector = normalize_embedding(
                np.mean(np.stack([item.embedding for item in interior]), axis=0)
            )
        except ValueError:
            return [], {
                "detail_status": "skipped",
                "reason": "aggregate_embedding_not_comparable",
                "music_premise": {
                    "state": premise_state,
                    "claim_id": premise_claim_id,
                    "evidence_refs": list(premise_evidence_refs),
                    "publication_allowed": publish_details,
                },
                "new_details": [],
                "static_details": [],
                "acoustic_changes": acoustic_changes,
                "signal_context": signal_context,
                "neighbor_hypotheses": [],
                "candidate_changes": [],
                "context_window_ids": [item.window_id for item in context],
            }

        existing_axis_ids = {
            reference.removeprefix("axis:")
            for claim in event.claims
            for reference in claim.evidence_refs
            if reference.startswith("axis:")
        }
        added: list[TimelineClaim] = []
        reports: list[dict[str, Any]] = []
        neighbor_hypotheses: list[dict[str, Any]] = []
        candidate_changes: list[dict[str, Any]] = []
        interior_ids = {item.window_id for item in interior}
        for axis, vectors in self.detail_axes:
            if axis.axis_id in existing_axis_ids:
                continue
            aggregate = self.matcher.match_axis(
                axis,
                aggregate_vector,
                vectors,
                policy=self.policy,
                model_revision=scene_claim.model_revision,
                evidence_refs=tuple(f"embedding:{item.window_id}" for item in interior),
            )
            aggregate_supported = (
                {item.candidate_id: item for item in aggregate.supported_candidates}
                if not axis.mutually_exclusive
                else (
                    {aggregate.candidate_id: aggregate.top_candidates[0]}
                    if aggregate.decision == "accepted" and aggregate.top_candidates
                    else {}
                )
            )
            per_window: list[tuple[str, set[str], SemanticClaim]] = []
            for window in interior:
                matched = self.matcher.match_axis(
                    axis,
                    window.embedding,
                    vectors,
                    policy=self.policy,
                    model_revision=window.model_revision,
                    evidence_refs=(f"audio:{window.start_ms}-{window.end_ms}",),
                )
                supported = (
                    {item.candidate_id for item in matched.supported_candidates}
                    if not axis.mutually_exclusive
                    else (
                        {matched.candidate_id}
                        if matched.decision == "accepted"
                        else set()
                    )
                )
                per_window.append((window.window_id, supported, matched))
            axis_neighbors: list[dict[str, Any]] = []
            for window in context:
                if window.window_id in interior_ids:
                    continue
                matched = self.matcher.match_axis(
                    axis,
                    window.embedding,
                    vectors,
                    policy=self.policy,
                    model_revision=window.model_revision,
                    evidence_refs=(f"audio:{window.start_ms}-{window.end_ms}",),
                )
                row = {
                    "axis_id": axis.axis_id,
                    "window_id": window.window_id,
                    "relation": "before_event"
                    if window.end_ms <= event.start_ms
                    else "after_event",
                    "candidate_id": matched.candidate_id,
                    "decision": matched.decision,
                    "raw_cosine": matched.raw_cosine,
                    "margin": matched.margin,
                }
                axis_neighbors.append(row)
                neighbor_hypotheses.append(row)
            aggregate_candidates = {
                candidate_id: candidate_score
                for candidate_id, candidate_score in aggregate_supported.items()
            }
            aggregate_candidates.update(
                {
                    candidate.candidate_id: candidate
                    for candidate in aggregate.top_candidates
                    if candidate.candidate_id not in aggregate_candidates
                }
            )
            for candidate_id, candidate_score in aggregate_candidates.items():
                support_ids = [
                    window_id
                    for window_id, supported, _matched in per_window
                    if candidate_id in supported
                ]
                aggregate_accepted = candidate_id in aggregate_supported
                confirmed = (
                    aggregate_accepted
                    and len(support_ids) >= self.minimum_support_windows
                )
                candidate = next(
                    item for item in axis.candidates if item.candidate_id == candidate_id
                )
                report = {
                    "axis_id": axis.axis_id,
                    "candidate_id": candidate_id,
                    "text_ru": candidate.text_ru,
                    "decision": "accepted" if confirmed else "uncertain",
                    "status": (
                        "confirmed" if confirmed and publish_details
                        else "exploratory_support" if confirmed
                        else "abstained"
                    ),
                    "publication_status": (
                        "published"
                        if confirmed and publish_details
                        else "suppressed_music_premise_not_confirmed"
                        if confirmed
                        else "not_supported"
                    ),
                    "premise_state": premise_state,
                    "aggregate_raw_cosine": candidate_score.raw_cosine,
                    "aggregate_decision": aggregate.decision,
                    "aggregate_supported": aggregate_accepted,
                    "in_event_window_count": len(interior),
                    "per_window_accepted_count": len(support_ids),
                    "support_window_ids": support_ids,
                    "required_support_windows": self.minimum_support_windows,
                    "window_scores": [
                        {
                            "window_id": window_id,
                            "decision": next(
                                (
                                    item.decision
                                    for item in matched.top_candidates
                                    if item.candidate_id == candidate_id
                                ),
                                "not_in_top_k",
                            ),
                            "raw_cosine": next(
                                (
                                    item.raw_cosine
                                    for item in matched.top_candidates
                                    if item.candidate_id == candidate_id
                                ),
                                None,
                            ),
                        }
                        for window_id, _supported, matched in per_window
                    ],
                }
                reports.append(report)
                if not confirmed:
                    continue
                candidate_changes.extend(
                    {
                        "axis_id": axis.axis_id,
                        "from_candidate_id": candidate_id,
                        "to_candidate_id": neighbor["candidate_id"],
                        "neighbor_window_id": neighbor["window_id"],
                        "neighbor_decision": neighbor["decision"],
                        "change_type": "semantic_candidate_change",
                    }
                    for neighbor in axis_neighbors
                    if neighbor["decision"] == "accepted"
                    and neighbor["candidate_id"] != candidate_id
                )
                window_by_id = {item.window_id: item for item in interior}
                refs = [
                    f"audio:{window_by_id[window_id].start_ms}-{window_by_id[window_id].end_ms}"
                    for window_id in support_ids
                ]
                refs.extend(f"embedding:{window_id}" for window_id in support_ids)
                refs.extend(
                    f"signal-summary:{window_id}"
                    for window_id in support_ids
                    if window_by_id[window_id].signal_summary
                )
                refs.extend((f"axis:{axis.axis_id}", f"l2:coarse-to-fine:{event.event_id}"))
                if publish_details:
                    added.append(
                        TimelineClaim(
                            claim_id=f"claim-l2-{axis.axis_id}-{candidate_id}-{event.event_id}",
                            label=candidate_id,
                            text_ru=candidate.text_ru,
                            decision="accepted",
                            raw_cosine=candidate_score.raw_cosine,
                            margin=max(
                                0.0,
                                candidate_score.raw_cosine - self.policy.minimum_similarity,
                            ),
                            evidence_refs=tuple(dict.fromkeys(refs)),
                            window_ids=tuple(support_ids),
                            model_revision=scene_claim.model_revision,
                            sample_count=len(support_ids),
                            premise_state=premise_state,
                            premise_claim_id=premise_claim_id,
                            premise_evidence_refs=premise_evidence_refs,
                        )
                    )
        return added, {
            "detail_status": (
                "confirmed"
                if added
                else "exploratory_only"
                if any(item["status"] == "exploratory_support" for item in reports)
                else "abstained"
            ),
            "reason": (
                None
                if added
                else "music_premise_not_confirmed"
                if not publish_details
                and any(item["status"] == "exploratory_support" for item in reports)
                else "no_detail_met_temporal_support"
            ),
            "music_premise": {
                "state": premise_state,
                "claim_id": premise_claim_id,
                "evidence_refs": list(premise_evidence_refs),
                "publication_allowed": publish_details,
            },
            "coarse_concept": {
                "axis_id": "music_presence",
                "candidate_id": scene_claim.label,
                "decision": scene_claim.decision,
            },
            "coarse_candidates": [
                {
                    "candidate_id": candidate_id,
                    "raw_cosine": raw_cosine,
                    "decision": decision,
                }
                for candidate_id, raw_cosine, decision in scene_claim.candidate_hypotheses
            ],
            "new_details": [claim.to_dict() for claim in added],
            "static_details": reports,
            "acoustic_changes": acoustic_changes,
            "signal_context": signal_context,
            "neighbor_hypotheses": neighbor_hypotheses,
            "candidate_changes": candidate_changes,
            "context_window_ids": [item.window_id for item in context],
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


def _music_scene_supports_details(
    candidate_id: str | None,
    decision: str | None,
    raw_cosine: float | None = None,
    candidate_hypotheses: tuple[tuple[str, float, str], ...] = (),
    *,
    minimum_similarity: float = 0.6,
) -> bool:
    music_candidates = {"music_present", "music_and_speech"}
    if (
        decision in {"accepted", "uncertain"}
        and candidate_id in music_candidates
        and raw_cosine is not None
        and raw_cosine >= minimum_similarity
    ):
        return True
    return any(
        hypothesis_id in music_candidates
        and score >= minimum_similarity
        and hypothesis_decision in {"accepted", "uncertain"}
        for hypothesis_id, score, hypothesis_decision in candidate_hypotheses
    )


def _music_premise_state(
    candidate_id: str | None,
    decision: str | None,
    raw_cosine: float | None,
    candidate_hypotheses: tuple[tuple[str, float, str], ...],
    *,
    minimum_similarity: float,
) -> str:
    """Separate an internal positive music possibility from a publishable premise."""
    if (
        candidate_id in {"music_present", "music_and_speech"}
        and decision == "accepted"
        and raw_cosine is not None
        and raw_cosine >= minimum_similarity
    ):
        return "music_confirmed"
    if candidate_id == "music_absent" and decision == "accepted":
        return "music_absent"
    if _music_scene_supports_details(
        candidate_id,
        decision,
        raw_cosine,
        candidate_hypotheses,
        minimum_similarity=minimum_similarity,
    ):
        return "music_possible"
    return "not_supported"
