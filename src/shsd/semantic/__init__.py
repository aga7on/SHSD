"""Versioned candidate profiles and conservative embedding matching."""

from shsd.semantic.hypotheses import (
    HypothesisAxis,
    HypothesisCandidate,
    HypothesisProfile,
    encode_profile_candidates,
    load_profiles,
)
from shsd.semantic.matcher import MatchPolicy, SemanticClaim, SemanticMatcher
from shsd.semantic.temporal import BoundedAudioEmbeddingHistory, TemporalAudioRefiner

__all__ = [
    "HypothesisAxis",
    "HypothesisCandidate",
    "HypothesisProfile",
    "MatchPolicy",
    "SemanticClaim",
    "SemanticMatcher",
    "BoundedAudioEmbeddingHistory",
    "TemporalAudioRefiner",
    "encode_profile_candidates",
    "load_profiles",
]
