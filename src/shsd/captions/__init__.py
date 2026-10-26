"""Evidence-bound caption generation."""

from shsd.captions.hypothesis_proposer import ProposalResult, QwenHypothesisProposer
from shsd.captions.narrator import (
    NarrationASRQuote,
    NarrationClaim,
    NarrationEventRef,
    NarrationRequest,
    NarrationResponse,
    NarrationResult,
    QwenNarrator,
)

__all__ = [
    "NarrationASRQuote",
    "NarrationClaim",
    "NarrationEventRef",
    "NarrationRequest",
    "NarrationResponse",
    "NarrationResult",
    "QwenNarrator",
    "ProposalResult",
    "QwenHypothesisProposer",
]
