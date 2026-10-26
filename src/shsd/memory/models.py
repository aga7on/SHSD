"""Validated JSON event and claim records."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class TimelineClaim:
    claim_id: str
    label: str
    text_ru: str | None
    decision: str
    raw_cosine: float | None
    margin: float | None
    evidence_refs: tuple[str, ...]
    window_ids: tuple[str, ...]
    model_revision: str
    sample_count: int

    def __post_init__(self) -> None:
        if not self.claim_id or not self.label or not self.model_revision:
            raise ValueError("claim_id, label, and model_revision must be non-empty")
        if self.sample_count < 1:
            raise ValueError("sample_count must be positive")
        if self.decision not in {"accepted", "uncertain", "rejected", "unverified", "unknown"}:
            raise ValueError("unsupported claim decision")
        if not self.evidence_refs and self.decision != "unverified":
            raise ValueError("claims require evidence_refs or the unverified decision")
        if self.raw_cosine is not None and (
            not math.isfinite(self.raw_cosine) or not -1.0 <= self.raw_cosine <= 1.0
        ):
            raise ValueError("raw_cosine must be finite and between -1 and 1")
        if self.margin is not None and (
            not math.isfinite(self.margin) or not 0.0 <= self.margin <= 2.0
        ):
            raise ValueError("margin must be finite and between 0 and 2")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["evidence_refs"] = list(self.evidence_refs)
        result["window_ids"] = list(self.window_ids)
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> TimelineClaim:
        return cls(
            claim_id=str(value["claim_id"]),
            label=str(value["label"]),
            text_ru=cast(str | None, value.get("text_ru")),
            decision=str(value["decision"]),
            raw_cosine=cast(float | None, value.get("raw_cosine")),
            margin=cast(float | None, value.get("margin")),
            evidence_refs=tuple(cast(list[str], value.get("evidence_refs", []))),
            window_ids=tuple(cast(list[str], value.get("window_ids", []))),
            model_revision=str(value["model_revision"]),
            sample_count=int(value.get("sample_count", 1)),
        )


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    stream_id: str
    epoch: int
    event_id: str
    revision: int
    start_ms: int
    end_ms: int
    kind: str
    level: str
    state: str
    modality_mask: dict[str, bool]
    claims: tuple[TimelineClaim, ...]
    caption_ru: str | None = None
    supersedes_revision: int | None = None
    schema_version: int = 1
    updated_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if not self.stream_id or not self.event_id or not self.kind:
            raise ValueError("stream_id, event_id, and kind must be non-empty")
        if self.epoch < 0 or self.revision < 1:
            raise ValueError("epoch must be non-negative and revision must be positive")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("event interval must satisfy 0 <= start_ms < end_ms")
        if self.level not in {"L0", "L1", "L2", "L3"}:
            raise ValueError("level must be one of L0, L1, L2, or L3")
        if self.state not in {"draft", "refined", "committed", "superseded"}:
            raise ValueError("unsupported event state")
        if self.schema_version != 1:
            raise ValueError("unsupported event schema version")
        if set(self.modality_mask) != {"audio", "video", "speech"} or not all(
            isinstance(enabled, bool) for enabled in self.modality_mask.values()
        ):
            raise ValueError("modality_mask must contain boolean audio, video, and speech keys")
        if self.revision == 1 and self.supersedes_revision is not None:
            raise ValueError("revision 1 cannot supersede another revision")
        if self.revision > 1 and self.supersedes_revision != self.revision - 1:
            raise ValueError("revisions must supersede the immediately previous revision")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["claims"] = [claim.to_dict() for claim in self.claims]
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> TimelineEvent:
        return cls(
            schema_version=int(value.get("schema_version", 1)),
            stream_id=str(value["stream_id"]),
            epoch=int(value["epoch"]),
            event_id=str(value["event_id"]),
            revision=int(value["revision"]),
            start_ms=int(value["start_ms"]),
            end_ms=int(value["end_ms"]),
            kind=str(value["kind"]),
            level=str(value["level"]),
            state=str(value["state"]),
            modality_mask=cast(dict[str, bool], value["modality_mask"]),
            claims=tuple(
                TimelineClaim.from_dict(cast(dict[str, Any], item))
                for item in cast(list[Any], value.get("claims", []))
            ),
            caption_ru=cast(str | None, value.get("caption_ru")),
            supersedes_revision=cast(int | None, value.get("supersedes_revision")),
            updated_at_utc=str(value["updated_at_utc"]),
        )
