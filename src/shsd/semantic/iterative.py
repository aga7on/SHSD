"""One bounded Qwen proposal pass, checked by the frozen embedding model."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Protocol

import numpy as np

from shsd.captions.hypothesis_proposer import ProposalResult
from shsd.embeddings.cache import normalize_embedding
from shsd.embeddings.provider import EmbeddingRecord
from shsd.semantic.hypotheses import HypothesisAxis, HypothesisCandidate
from shsd.semantic.matcher import MatchPolicy, RankedCandidate, SemanticClaim, SemanticMatcher


class TextEncoder(Protocol):
    def encode_texts(
        self, candidates: list[str], *, cache_namespace: str = ""
    ) -> list[EmbeddingRecord]: ...


class CandidateProposer(Protocol):
    def propose(
        self, axis: HypothesisAxis, top_candidates: tuple[RankedCandidate, ...]
    ) -> ProposalResult: ...


@dataclass(frozen=True, slots=True)
class ExpandedHypotheses:
    axis: HypothesisAxis
    vectors: Mapping[str, np.ndarray]
    proposal_count: int
    proposal_latency_ms: float
    embedding_latency_ms: float


@dataclass(frozen=True, slots=True)
class IterationOutcome:
    axis: HypothesisAxis
    vectors: Mapping[str, np.ndarray]
    baseline: SemanticClaim
    selected: SemanticClaim
    report: dict[str, object] | None


class IterativeHypothesisRefiner:
    """Use Qwen to suggest strings once; only EmbeddingGemma can support them."""

    def __init__(
        self,
        *,
        axis_id: str,
        encoder: TextEncoder,
        proposer: CandidateProposer,
        cpu_budget_ms: float = 15_000,
    ) -> None:
        if not axis_id:
            raise ValueError("axis_id must be non-empty")
        if not 100 <= cpu_budget_ms <= 30_000:
            raise ValueError("cpu_budget_ms must be between 100 and 30000")
        self.axis_id = axis_id
        self.encoder = encoder
        self.proposer = proposer
        self.cpu_budget_ms = cpu_budget_ms
        self._attempted: set[str] = set()
        self._expanded: dict[str, ExpandedHypotheses] = {}

    def match(
        self,
        axis: HypothesisAxis,
        media_embedding: np.ndarray,
        candidate_vectors: Mapping[str, np.ndarray],
        *,
        matcher: SemanticMatcher,
        policy: MatchPolicy,
        model_revision: str,
        evidence_refs: tuple[str, ...],
    ) -> IterationOutcome:
        baseline = matcher.match_axis(
            axis,
            media_embedding,
            candidate_vectors,
            policy=policy,
            model_revision=model_revision,
            evidence_refs=evidence_refs,
        )
        if axis.axis_id != self.axis_id:
            return IterationOutcome(axis, candidate_vectors, baseline, baseline, None)

        expanded = self._expanded.get(axis.axis_id)
        reused = expanded is not None
        report: dict[str, object] | None = None
        if expanded is None and axis.axis_id not in self._attempted:
            if baseline.decision != "accepted":
                self._attempted.add(axis.axis_id)
                expanded, report = self._propose_once(
                    axis, baseline, candidate_vectors
                )
        if expanded is None:
            if report is None:
                report = self._attempt_report(axis, baseline, "baseline_only")
            return IterationOutcome(axis, candidate_vectors, baseline, baseline, report)

        iterated = matcher.match_axis(
            expanded.axis,
            media_embedding,
            expanded.vectors,
            policy=policy,
            model_revision=model_revision,
            evidence_refs=evidence_refs,
        )
        selected = (
            iterated
            if baseline.decision != "accepted" and iterated.decision == "accepted"
            else baseline
        )
        report = {
            "record_type": "hypothesis_iteration",
            "axis_id": axis.axis_id,
            "status": "reused" if reused else "rescored",
            "baseline": self._claim_summary(baseline),
            "iterated": self._claim_summary(iterated),
            "selected_candidate_id": selected.candidate_id,
            "selected_decision": selected.decision,
            "generated_candidate_ids": [
                item.candidate_id
                for item in expanded.axis.candidates
                if item.candidate_id.startswith("iterative_")
            ],
            "proposal_latency_ms": expanded.proposal_latency_ms,
            "embedding_latency_ms": expanded.embedding_latency_ms,
            "cpu_budget_ms": self.cpu_budget_ms,
        }
        return IterationOutcome(expanded.axis, expanded.vectors, baseline, selected, report)

    def _propose_once(
        self,
        axis: HypothesisAxis,
        baseline: SemanticClaim,
        base_vectors: Mapping[str, np.ndarray],
    ) -> tuple[ExpandedHypotheses | None, dict[str, object] | None]:
        started = time.perf_counter()
        try:
            proposal = self.proposer.propose(axis, baseline.top_candidates)
            proposal_elapsed_ms = (time.perf_counter() - started) * 1000
            if proposal_elapsed_ms > self.cpu_budget_ms:
                return None, self._attempt_report(
                    axis,
                    baseline,
                    "cpu_budget_exceeded",
                    proposal_latency_ms=proposal.latency_ms,
                )
            candidates = tuple(
                candidate
                for candidate in proposal.candidates
                if candidate.candidate_id not in {item.candidate_id for item in axis.candidates}
            )[:6]
            if not candidates:
                return None, self._attempt_report(
                    axis, baseline, "no_candidates", proposal_latency_ms=proposal.latency_ms
                )

            namespace_payload = {
                "axis_id": axis.axis_id,
                "existing": [(item.candidate_id, item.text_en) for item in axis.candidates],
                "generated": [(item.candidate_id, item.text_en) for item in candidates],
            }
            namespace_hash = hashlib.sha256(
                json.dumps(namespace_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            embedding_started = time.perf_counter()
            records = self.encoder.encode_texts(
                [item.text_en for item in candidates],
                cache_namespace=f"iterative:{axis.axis_id}:{namespace_hash}",
            )
            embedding_latency_ms = (time.perf_counter() - embedding_started) * 1000
            if (time.perf_counter() - started) * 1000 > self.cpu_budget_ms:
                return None, self._attempt_report(
                    axis,
                    baseline,
                    "cpu_budget_exceeded",
                    proposal_latency_ms=proposal.latency_ms,
                    embedding_latency_ms=embedding_latency_ms,
                )
            if len(records) != len(candidates):
                raise RuntimeError("text encoder returned the wrong number of candidate vectors")

            accepted: list[tuple[HypothesisCandidate, EmbeddingRecord]] = []
            reference_vectors = [normalize_embedding(vector) for vector in base_vectors.values()]
            accepted_vectors: list[np.ndarray] = []
            for candidate, record in zip(candidates, records, strict=True):
                vector = normalize_embedding(record.embedding)
                duplicate = any(
                    float(np.dot(vector, reference)) >= 0.92
                    for reference in (*reference_vectors, *accepted_vectors)
                )
                if duplicate:
                    continue
                accepted.append((candidate, record))
                accepted_vectors.append(vector)
            if not accepted:
                return None, self._attempt_report(
                    axis,
                    baseline,
                    "no_distinct_candidates",
                    proposal_latency_ms=proposal.latency_ms,
                    embedding_latency_ms=embedding_latency_ms,
                )

            candidates = tuple(
                replace(candidate, candidate_id=f"iterative_{index}")
                for index, (candidate, _record) in enumerate(accepted, start=1)
            )
            records = [record for _candidate, record in accepted]

            expanded_axis = replace(axis, candidates=(*axis.candidates, *candidates))
            expanded_vectors = dict(base_vectors)
            expanded_vectors.update(
                {
                    candidate.candidate_id: record.embedding
                    for candidate, record in zip(candidates, records, strict=True)
                }
            )
            expanded = ExpandedHypotheses(
                expanded_axis,
                expanded_vectors,
                len(candidates),
                proposal.latency_ms,
                round(embedding_latency_ms, 3),
            )
            self._expanded[axis.axis_id] = expanded
            return expanded, None
        except Exception as error:
            return None, self._attempt_report(
                axis,
                baseline,
                "proposal_failed",
                error=f"{type(error).__name__}: {error}"[:300],
            )

    @staticmethod
    def _claim_summary(claim: SemanticClaim) -> dict[str, object]:
        return {
            "candidate_id": claim.candidate_id,
            "decision": claim.decision,
            "raw_cosine": claim.raw_cosine,
            "margin": claim.margin,
        }

    @classmethod
    def _attempt_report(
        cls,
        axis: HypothesisAxis,
        baseline: SemanticClaim,
        status: str,
        *,
        proposal_latency_ms: float = 0.0,
        embedding_latency_ms: float = 0.0,
        error: str | None = None,
    ) -> dict[str, object]:
        report: dict[str, object] = {
            "record_type": "hypothesis_iteration",
            "axis_id": axis.axis_id,
            "status": status,
            "baseline": cls._claim_summary(baseline),
            "iterated": cls._claim_summary(baseline),
            "selected_candidate_id": baseline.candidate_id,
            "selected_decision": baseline.decision,
            "generated_candidate_ids": [],
            "proposal_latency_ms": proposal_latency_ms,
            "embedding_latency_ms": embedding_latency_ms,
        }
        if error is not None:
            report["error"] = error
        return report
