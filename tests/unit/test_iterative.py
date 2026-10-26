from __future__ import annotations

import numpy as np

from shsd.captions.hypothesis_proposer import ProposalResult, QwenHypothesisProposer
from shsd.embeddings.provider import EmbeddingRecord
from shsd.semantic import HypothesisAxis, HypothesisCandidate
from shsd.semantic.iterative import IterativeHypothesisRefiner
from shsd.semantic.matcher import MatchPolicy, RankedCandidate, SemanticMatcher

REVISION = "test-embedding-revision"


def _axis() -> HypothesisAxis:
    return HypothesisAxis(
        axis_id="instrument_family",
        modality="audio",
        mutually_exclusive=True,
        candidates=(
            HypothesisCandidate(
                "synth", "A synthesized timbre is audible.", "Слышен синтезаторный тембр.",
                "positive", (),
            ),
            HypothesisCandidate(
                "strings", "An acoustic string timbre is audible.", "Слышен тембр струнных.",
                "positive", (),
            ),
        ),
    )


def _candidate() -> HypothesisCandidate:
    return HypothesisCandidate(
        "iterative_1",
        "A muted electric guitar is audible.",
        "Слышна приглушённая электрогитара.",
        "positive",
        (),
    )


class FakeProposer:
    def __init__(self, candidates: tuple[HypothesisCandidate, ...]) -> None:
        self.candidates = candidates
        self.calls = 0

    def propose(
        self, axis: HypothesisAxis, top_candidates: tuple[RankedCandidate, ...]
    ) -> ProposalResult:
        del axis, top_candidates
        self.calls += 1
        return ProposalResult(self.candidates, latency_ms=5.0)


class FakeEncoder:
    def __init__(self, vector: np.ndarray) -> None:
        self.vector = vector
        self.namespaces: list[str] = []

    def encode_texts(
        self, candidates: list[str], *, cache_namespace: str = ""
    ) -> list[EmbeddingRecord]:
        self.namespaces.append(cache_namespace)
        return [
            EmbeddingRecord(
                embedding=self.vector,
                model_revision=REVISION,
                input_preprocess_version="test-v1",
                modality="text",
                embedding_dim=768,
                norm=float(np.linalg.norm(self.vector)),
                created_at="2026-10-26T00:00:00+00:00",
                latency_ms=1.0,
                window_id=f"text:{index}",
                interval_ms=None,
                cache_hit=False,
            )
            for index, _ in enumerate(candidates)
        ]


def test_qwen_output_parser_limits_and_deduplicates_candidates() -> None:
    axis = _axis()
    output = (
        "Assistant:\n```json\n"
        '{"candidates":['
        '{"text_en":"A muted electric guitar is audible.",'
        '"text_ru":"Слышна приглушённая электрогитара."},'
        '{"text_en":"A muted electric guitar is audible.",'
        '"text_ru":"Повторный кандидат."},'
        '{"text_en":"Not an English claim","text_ru":"No Cyrillic"}'
        "]}\n```"
    )

    candidates = QwenHypothesisProposer._parse_candidates(output, axis, limit=6)

    assert len(candidates) == 1
    assert candidates[0].candidate_id == "iterative_1"
    assert candidates[0].text_en.startswith("A muted")


def test_generated_hypothesis_needs_embedding_support_and_runs_only_once() -> None:
    axis = _axis()
    media = np.zeros(768, dtype=np.float32)
    media[0] = 1.0
    first_base = np.zeros(768, dtype=np.float32)
    first_base[1] = 1.0
    second_base = np.zeros(768, dtype=np.float32)
    second_base[2] = 1.0
    unsupported = np.zeros(768, dtype=np.float32)
    unsupported[3] = 1.0
    base_vectors = {"synth": first_base, "strings": second_base}
    proposer = FakeProposer((_candidate(),))
    refiner = IterativeHypothesisRefiner(
        axis_id="instrument_family",
        encoder=FakeEncoder(unsupported),
        proposer=proposer,
    )
    matcher = SemanticMatcher()
    policy = MatchPolicy(0.6, 0.05, top_k=1)

    first = refiner.match(
        axis,
        media,
        base_vectors,
        matcher=matcher,
        policy=policy,
        model_revision=REVISION,
        evidence_refs=("audio:0-1000",),
    )
    second = refiner.match(
        axis,
        media,
        base_vectors,
        matcher=matcher,
        policy=policy,
        model_revision=REVISION,
        evidence_refs=("audio:1000-2000",),
    )

    assert first.baseline.candidate_id == "unknown"
    assert first.selected.candidate_id == "unknown"
    assert first.report is not None and first.report["status"] == "rescored"
    assert second.report is not None and second.report["status"] == "reused"
    assert second.selected.candidate_id == "unknown"
    assert proposer.calls == 1


def test_independently_scored_candidate_can_fill_baseline_abstention() -> None:
    axis = _axis()
    media = np.zeros(768, dtype=np.float32)
    media[0] = 1.0
    unsupported = np.zeros(768, dtype=np.float32)
    unsupported[1] = 1.0
    refiner = IterativeHypothesisRefiner(
        axis_id="instrument_family",
        encoder=FakeEncoder(media),
        proposer=FakeProposer((_candidate(),)),
    )

    outcome = refiner.match(
        axis,
        media,
        {"synth": unsupported, "strings": unsupported},
        matcher=SemanticMatcher(),
        policy=MatchPolicy(0.6, 0.05, top_k=1),
        model_revision=REVISION,
        evidence_refs=("audio:0-1000",),
    )

    assert outcome.baseline.candidate_id == "unknown"
    assert outcome.selected.candidate_id == "iterative_1"
    assert outcome.selected.decision == "accepted"
    assert outcome.report is not None
    assert outcome.report["iterated"]["candidate_id"] == "iterative_1"  # type: ignore[index]


def test_semantic_paraphrase_of_existing_candidate_is_not_added() -> None:
    axis = _axis()
    media = np.zeros(768, dtype=np.float32)
    media[0] = 1.0
    existing = np.zeros(768, dtype=np.float32)
    existing[1] = 1.0
    refiner = IterativeHypothesisRefiner(
        axis_id="instrument_family",
        encoder=FakeEncoder(existing),
        proposer=FakeProposer((_candidate(),)),
    )

    outcome = refiner.match(
        axis,
        media,
        {"synth": existing, "strings": existing},
        matcher=SemanticMatcher(),
        policy=MatchPolicy(0.6, 0.05, top_k=1),
        model_revision=REVISION,
        evidence_refs=("audio:0-1000",),
    )

    assert outcome.report is not None
    assert outcome.report["status"] == "no_distinct_candidates"
    assert outcome.selected.candidate_id == "unknown"
