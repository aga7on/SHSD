"""Shared contracts for cheap, reproducible signal observations."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class SignalObservation:
    """One measured value with a source-time interval and method provenance."""

    start_ms: int
    end_ms: int
    subtype: str
    quality: float
    method_version: str
    value: float | bool
    unit: str

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("observation interval must satisfy 0 <= start_ms < end_ms")
        if not math.isfinite(self.quality) or not 0.0 <= self.quality <= 1.0:
            raise ValueError("quality must be finite and between 0 and 1")
        if not self.subtype or not self.method_version:
            raise ValueError("subtype and method_version must be non-empty")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("observation value must be finite")

    def to_dict(self) -> dict[str, int | float | bool | str]:
        """Return a JSON-compatible representation."""
        return asdict(self)
