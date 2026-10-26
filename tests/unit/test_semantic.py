from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from shsd.embeddings.provider import EmbeddingProvider, EmbeddingRecord
from shsd.semantic import HypothesisAxis, HypothesisCandidate, MatchPolicy, SemanticMatcher
from shsd.semantic.hypotheses import encode_profile_candidates, load_profiles

ROOT = Path(__file__).resolve().parents[2]
REVISION = "914f7f89142e33e77833254d9c9b90c3cef7303b"


def _axis() -> HypothesisAxis:
    return HypothesisAxis(
        axis_id="music_presence",
        modality="audio",
        mutually_exclusive=True,
        candidates=(
            HypothesisCandidate(
                "music", "Music is audible.", "Слышна музыка.", "positive", ("no_music",)
            ),
            HypothesisCandidate(
                "no_music", "No music is audible.", "Музыка не слышна.", "negative", ("music",)
            ),
        ),
    )


def test_profiles_have_competing_candidates_and_non_embedded_unknown() -> None:
    profiles = load_profiles(
        ROOT / "configs" / "hypotheses", expected_model_revision=REVISION
    )
    assert {profile.profile_id for profile in profiles} == {"music", "sound", "visual", "av"}
    assert sum(len(profile.axes) for profile in profiles) >= 10
    assert all(
        len(axis.candidates) >= 2
        and all(candidate.text_en and candidate.text_ru for candidate in axis.candidates)
        for profile in profiles
        for axis in profile.axes
    )
    assert all(profile.unknown_id == "unknown" for profile in profiles)
    assert all(len(profile.candidate_fingerprint()) == 64 for profile in profiles)
    assert profiles[0].candidate_fingerprint() != replace(
        profiles[0], model_revision="different-model-revision"
    ).candidate_fingerprint()


def test_profile_revision_must_match_loaded_embedding_model() -> None:
    with pytest.raises(ValueError, match="does not match"):
        load_profiles(ROOT / "configs" / "hypotheses", expected_model_revision="stale")


def test_profile_vectors_use_candidate_fingerprint_namespace() -> None:
    profile = load_profiles(ROOT / "configs" / "hypotheses", expected_model_revision=REVISION)[0]

    class FakeProvider(EmbeddingProvider):
        def __init__(self) -> None:
            self.cache_namespace = ""

        def encode_texts(
            self, candidates: list[str], *, cache_namespace: str = ""
        ) -> list[EmbeddingRecord]:
            self.cache_namespace = cache_namespace
            vector = np.ones(768, dtype=np.float32) / np.sqrt(768)
            return [
                EmbeddingRecord(
                    embedding=vector,
                    model_revision=REVISION,
                    input_preprocess_version="test-v1",
                    modality="text",
                    embedding_dim=768,
                    norm=1.0,
                    created_at="2026-10-25T00:00:00+00:00",
                    latency_ms=0.1,
                    window_id=f"text:{index}",
                    interval_ms=None,
                    cache_hit=False,
                )
                for index, _ in enumerate(candidates)
            ]

    provider = FakeProvider()
    vectors = encode_profile_candidates(profile, provider)
    assert provider.cache_namespace == f"{profile.profile_id}:{profile.candidate_fingerprint()}"
    assert len(vectors) == len(profile.axes)
    assert all(len(vectors[axis.axis_id]) == len(axis.candidates) for axis in profile.axes)


def test_matcher_accepts_only_a_clear_candidate_and_keeps_raw_cosine() -> None:
    axis = _axis()
    media = np.zeros(768, dtype=np.float32)
    music = np.zeros_like(media)
    no_music = np.zeros_like(media)
    media[0] = music[0] = 1.0
    no_music[1] = 1.0

    claim = SemanticMatcher().match_axis(
        axis,
        media,
        {"music": music, "no_music": no_music},
        policy=MatchPolicy(minimum_similarity=0.5, minimum_margin=0.1),
        model_revision=REVISION,
        evidence_refs=("audio:0-1000",),
    )

    assert claim.candidate_id == "music"
    assert claim.decision == "accepted"
    assert claim.raw_cosine == pytest.approx(1.0)
    assert claim.margin == pytest.approx(1.0)
    assert claim.evidence_refs == ("audio:0-1000",)
    assert claim.to_dict()["raw_cosine"] == pytest.approx(1.0)


def test_matcher_abstains_below_threshold_and_marks_small_margin_uncertain() -> None:
    axis = _axis()
    first = np.zeros(768, dtype=np.float32)
    second = np.zeros_like(first)
    orthogonal = np.zeros_like(first)
    first[0] = orthogonal[2] = 1.0
    second[1] = 1.0
    vectors = {"music": first, "no_music": second}
    matcher = SemanticMatcher()
    policy = MatchPolicy(minimum_similarity=0.5, minimum_margin=0.1)

    unknown = matcher.match_axis(
        axis, orthogonal, vectors, policy=policy, model_revision=REVISION
    )
    ambiguous_query = (first + second) / np.sqrt(2.0)
    uncertain = matcher.match_axis(
        axis, ambiguous_query, vectors, policy=policy, model_revision=REVISION
    )

    assert unknown.candidate_id == "unknown"
    assert unknown.text_ru is None
    assert unknown.decision == "uncertain"
    assert uncertain.candidate_id == "music"
    assert uncertain.decision == "uncertain"
    assert {item.decision for item in uncertain.top_candidates} == {"uncertain"}


def test_non_exclusive_axis_accepts_independently_supported_candidates_outside_top_k() -> None:
    axis = HypothesisAxis(
        axis_id="instrument_family",
        modality="audio",
        mutually_exclusive=False,
        candidates=(
            HypothesisCandidate("synth", "Synth timbre.", "Синтезаторный тембр.", "positive", ()),
            HypothesisCandidate("strings", "String timbre.", "Струнный тембр.", "positive", ()),
            HypothesisCandidate("brass", "Brass timbre.", "Медный тембр.", "positive", ()),
        ),
    )
    media = np.zeros(768, dtype=np.float32)
    media[0] = 1.0
    vectors = {
        "synth": np.eye(1, 768, 0, dtype=np.float32).reshape(-1),
        "strings": np.array([0.8, 0.6] + [0.0] * 766, dtype=np.float32),
        "brass": np.eye(1, 768, 2, dtype=np.float32).reshape(-1),
    }

    claim = SemanticMatcher().match_axis(
        axis,
        media,
        vectors,
        policy=MatchPolicy(minimum_similarity=0.65, minimum_margin=0.05, top_k=1),
        model_revision=REVISION,
        evidence_refs=("audio:0-1000",),
    )

    assert claim.decision == "accepted"
    assert {item.candidate_id for item in claim.supported_candidates} == {"synth", "strings"}
    assert len(claim.top_candidates) == 1
    assert claim.evidence_refs == ("audio:0-1000",)
