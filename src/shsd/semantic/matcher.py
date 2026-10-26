"""Cosine candidate ranking with explicit abstention and no probability claims."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass

import numpy as np

from shsd.embeddings.cache import normalize_embedding
from shsd.semantic.hypotheses import HypothesisAxis, HypothesisCandidate


@dataclass(frozen=True, slots=True)
class MatchPolicy:
    minimum_similarity: float
    minimum_margin: float
    top_k: int = 3

    def __post_init__(self) -> None:
        if not -1.0 <= self.minimum_similarity <= 1.0:
            raise ValueError("minimum_similarity must be between -1 and 1")
        if not 0.0 <= self.minimum_margin <= 2.0:
            raise ValueError("minimum_margin must be between 0 and 2")
        if self.top_k < 1:
            raise ValueError("top_k must be positive")


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate_id: str
    text_ru: str
    raw_cosine: float
    decision: str


@dataclass(frozen=True, slots=True)
class SemanticClaim:
    axis_id: str
    candidate_id: str
    text_ru: str | None
    decision: str
    raw_cosine: float
    margin: float
    model_revision: str
    evidence_refs: tuple[str, ...]
    top_candidates: tuple[RankedCandidate, ...]
    supported_candidates: tuple[RankedCandidate, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SemanticMatcher:
    """Rank a single axis and abstain when score or competitor margin is weak."""

    def match_axis(
        self,
        axis: HypothesisAxis,
        media_embedding: np.ndarray,
        candidate_embeddings: Mapping[str, np.ndarray],
        *,
        policy: MatchPolicy,
        model_revision: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> SemanticClaim:
        media = normalize_embedding(media_embedding)
        missing = [
            candidate.candidate_id
            for candidate in axis.candidates
            if candidate.candidate_id not in candidate_embeddings
        ]
        if missing:
            raise ValueError(
                f"missing candidate embeddings for {axis.axis_id}: {', '.join(missing)}"
            )

        scored = [
            (
                candidate,
                float(
                    np.dot(media, normalize_embedding(candidate_embeddings[candidate.candidate_id]))
                ),
            )
            for candidate in axis.candidates
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        if not axis.mutually_exclusive:
            return self._match_independent_candidates(
                axis,
                scored,
                policy=policy,
                model_revision=model_revision,
                evidence_refs=evidence_refs,
            )

        best_candidate, best_score = scored[0]
        second_score = scored[1][1] if len(scored) > 1 else -1.0
        margin = best_score - second_score
        above_threshold = best_score >= policy.minimum_similarity
        decisive = above_threshold and margin >= policy.minimum_margin
        if not above_threshold:
            claim_id = "unknown"
            claim_text = None
            decision = "uncertain"
        else:
            claim_id = best_candidate.candidate_id
            claim_text = best_candidate.text_ru
            decision = "accepted" if decisive else "uncertain"

        top = tuple(
            RankedCandidate(
                candidate_id=candidate.candidate_id,
                text_ru=candidate.text_ru,
                raw_cosine=score,
                decision=(
                    decision
                    if candidate.candidate_id == best_candidate.candidate_id
                    else "uncertain"
                    if above_threshold and best_score - score < policy.minimum_margin
                    else "rejected"
                ),
            )
            for candidate, score in scored[: policy.top_k]
        )
        return SemanticClaim(
            axis_id=axis.axis_id,
            candidate_id=claim_id,
            text_ru=claim_text,
            decision=decision,
            raw_cosine=best_score,
            margin=margin,
            model_revision=model_revision,
            evidence_refs=evidence_refs,
            top_candidates=top,
        )

    @staticmethod
    def _match_independent_candidates(
        axis: HypothesisAxis,
        scored: list[tuple[HypothesisCandidate, float]],
        *,
        policy: MatchPolicy,
        model_revision: str,
        evidence_refs: tuple[str, ...],
    ) -> SemanticClaim:
        """Score each non-exclusive claim against its own threshold and persistence gate."""
        if not scored:
            raise ValueError(f"axis {axis.axis_id} has no candidates")
        decisions = {
            candidate.candidate_id: (
                "accepted"
                if score >= policy.minimum_similarity
                and score - policy.minimum_similarity >= policy.minimum_margin
                else "uncertain"
                if score >= policy.minimum_similarity
                else "rejected"
            )
            for candidate, score in scored
        }
        ranked = tuple(
            RankedCandidate(
                candidate_id=candidate.candidate_id,
                text_ru=candidate.text_ru,
                raw_cosine=score,
                decision=decisions[candidate.candidate_id],
            )
            for candidate, score in scored[: policy.top_k]
        )
        accepted = tuple(
            RankedCandidate(
                candidate_id=candidate.candidate_id,
                text_ru=candidate.text_ru,
                raw_cosine=score,
                decision="accepted",
            )
            for candidate, score in scored
            if decisions[candidate.candidate_id] == "accepted"
        )
        best_candidate, best_score = scored[0]
        selected = next(
            (
                (candidate, score)
                for candidate, score in scored
                if decisions[candidate.candidate_id] == "accepted"
            ),
            (best_candidate, best_score),
        )
        selected_candidate, selected_score = selected
        any_supported = bool(accepted)
        above_threshold = best_score >= policy.minimum_similarity
        return SemanticClaim(
            axis_id=axis.axis_id,
            candidate_id=(
                selected_candidate.candidate_id if above_threshold else "unknown"
            ),
            text_ru=selected_candidate.text_ru if above_threshold else None,
            decision="accepted" if any_supported else "uncertain",
            raw_cosine=selected_score,
            margin=max(0.0, selected_score - policy.minimum_similarity),
            model_revision=model_revision,
            evidence_refs=evidence_refs,
            top_candidates=ranked,
            supported_candidates=accepted,
        )
