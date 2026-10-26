"""Bounded local Qwen narration over accepted, timestamped evidence only."""

from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

from shsd.models.artifacts import verify_local_artifacts

PROMPT_VERSION = "narrator-ru-v2"
DEFAULT_MAX_TOKENS = 128
DEFAULT_TIMEOUT_SECONDS = 45.0
DEFAULT_MAX_INPUT_CHARS = 4_096
_TOKEN_PATTERN = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")
_RUSSIAN_SUFFIXES = tuple(
    sorted(
        {
            "иями",
            "ями",
            "ами",
            "ыми",
            "ими",
            "ого",
            "его",
            "ому",
            "ему",
            "ую",
            "юю",
            "ая",
            "яя",
            "ое",
            "ее",
            "ые",
            "ие",
            "ых",
            "их",
            "ым",
            "им",
            "ом",
            "ем",
            "ой",
            "ей",
            "ый",
            "ий",
            "ешь",
            "ишь",
            "ете",
            "ите",
            "ала",
            "яла",
            "ило",
            "или",
            "ают",
            "яют",
            "ует",
            "уют",
            "ает",
            "яет",
            "ит",
            "ет",
            "ат",
            "ят",
            "ут",
            "ют",
            "яли",
            "ели",
            "ить",
            "еть",
            "ать",
            "ять",
            "ены",
            "ена",
            "ено",
            "ией",
            "иям",
            "иях",
            "ия",
            "ии",
            "ью",
            "ов",
            "ев",
            "ам",
            "ям",
            "ах",
            "ях",
            "а",
            "я",
            "е",
            "и",
            "о",
            "у",
            "ю",
            "ы",
            "ь",
        },
        key=len,
        reverse=True,
    )
)
_RUSSIAN_FUNCTION_WORDS = frozenset(
    {
        "а",
        "и",
        "но",
        "в",
        "во",
        "на",
        "с",
        "со",
        "из",
        "к",
        "ко",
        "по",
        "о",
        "об",
        "от",
        "за",
        "при",
        "для",
        "над",
        "под",
        "между",
        "перед",
        "после",
        "у",
        "без",
        "это",
        "же",
        "ли",
        "как",
        "что",
        "цитата",
    }
)
_RUSSIAN_PROVENANCE_EQUIVALENTS = (
    frozenset({"слышн", "слыш", "звуч"}),
    frozenset({"изображен", "кадр"}),
    frozenset({"изменен", "меня", "смен"}),
)
_CLAIM_COVERAGE_THRESHOLD = 0.75
_CLAIM_COVERAGE_METHOD = "conservative_token_overlap_v2"


@dataclass(frozen=True, slots=True)
class NarrationEventRef:
    event_id: str
    revision: int

    def __post_init__(self) -> None:
        if not self.event_id or self.revision < 1:
            raise ValueError("event_id and positive revision are required")


@dataclass(frozen=True, slots=True)
class NarrationClaim:
    claim_id: str
    event_id: str
    revision: int
    start_ms: int
    end_ms: int
    text_ru: str
    decision: Literal["accepted"] = "accepted"
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.claim_id or not self.event_id or self.revision < 1:
            raise ValueError("claim, event, and revision IDs are required")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("claim interval must satisfy 0 <= start_ms < end_ms")
        if not self.text_ru.strip():
            raise ValueError("accepted claims require Russian display text")
        if self.decision != "accepted":
            raise ValueError("the narrator accepts only accepted claims")
        if not self.evidence_refs:
            raise ValueError("accepted claims require evidence references")


@dataclass(frozen=True, slots=True)
class NarrationASRQuote:
    segment_id: str
    start_ms: int
    end_ms: int
    text: str
    quality: float
    source: str

    def __post_init__(self) -> None:
        if not self.segment_id or not self.source or not self.text.strip():
            raise ValueError("ASR segment ID, source, and text are required")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("ASR interval must satisfy 0 <= start_ms < end_ms")
        if not 0.0 <= self.quality <= 1.0:
            raise ValueError("ASR quality must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class NarrationRequest:
    stream_id: str
    epoch: int
    event_refs: tuple[NarrationEventRef, ...]
    claims: tuple[NarrationClaim, ...]
    asr_quotes: tuple[NarrationASRQuote, ...] = ()
    state: dict[str, object] | None = None
    delta: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if not self.stream_id or self.epoch < 0:
            raise ValueError("stream_id and non-negative epoch are required")
        if not self.event_refs:
            raise ValueError("narration requires at least one event reference")
        if not self.claims and not self.asr_quotes:
            raise ValueError("narration requires an accepted claim or ASR quote")
        if len({item.event_id for item in self.event_refs}) != len(self.event_refs):
            raise ValueError("event references must be unique")
        if len({item.claim_id for item in self.claims}) != len(self.claims):
            raise ValueError("claim IDs must be unique")
        if len({item.segment_id for item in self.asr_quotes}) != len(self.asr_quotes):
            raise ValueError("ASR segment IDs must be unique")
        event_revisions = {(item.event_id, item.revision) for item in self.event_refs}
        if any((item.event_id, item.revision) not in event_revisions for item in self.claims):
            raise ValueError("every claim must reference a supplied event revision")

    @property
    def time_range(self) -> tuple[int, int]:
        intervals = [(claim.start_ms, claim.end_ms) for claim in self.claims] + [
            (quote.start_ms, quote.end_ms) for quote in self.asr_quotes
        ]
        return min(item[0] for item in intervals), max(item[1] for item in intervals)

    @property
    def source_ids(self) -> frozenset[str]:
        return frozenset(
            [claim.claim_id for claim in self.claims]
            + [quote.segment_id for quote in self.asr_quotes]
        )

    def facts_payload(self) -> dict[str, object]:
        # Repeated detector claims in adjacent windows do not add new facts.
        # Keep one readable instance in the prompt while retaining every input
        # claim/event ID for post-generation coverage accounting.
        accepted_claims: list[dict[str, object]] = []
        groups_by_signature: dict[str, dict[str, Any]] = {}
        for claim in self.claims:
            signature = CaptionDeduplicator.signature(claim.text_ru)
            group = groups_by_signature.get(signature)
            if group is not None:
                start_ms = int(group["start_ms"])
                end_ms = int(group["end_ms"])
                adjacent = claim.start_ms <= end_ms + 5_000 and claim.end_ms >= start_ms - 5_000
                if adjacent:
                    group["start_ms"] = min(start_ms, claim.start_ms)
                    group["end_ms"] = max(end_ms, claim.end_ms)
                    group["source_claim_ids"] = [
                        *cast(list[str], group["source_claim_ids"]),
                        claim.claim_id,
                    ]
                    group["evidence_refs"] = list(
                        dict.fromkeys(
                            [*cast(list[str], group["evidence_refs"]), *claim.evidence_refs]
                        )
                    )[:24]
                    group["source_event_revisions"] = list(
                        dict.fromkeys(
                            [
                                *cast(list[tuple[str, int]], group["source_event_revisions"]),
                                (claim.event_id, claim.revision),
                            ]
                        )
                    )
                    continue
            item = asdict(claim)
            item["source_claim_ids"] = [claim.claim_id]
            item["source_event_revisions"] = [(claim.event_id, claim.revision)]
            groups_by_signature[signature] = item
            accepted_claims.append(item)
        return {
            "stream_id": self.stream_id,
            "epoch": self.epoch,
            "event_revisions": [asdict(item) for item in self.event_refs],
            "accepted_claims": accepted_claims,
            "asr_quotes": [asdict(item) for item in self.asr_quotes],
            "state": self.state,
            "delta": self.delta,
            "time_range": {"start_ms": self.time_range[0], "end_ms": self.time_range[1]},
        }


def _coverage_stem(token: str) -> str:
    normalized = token.casefold().replace("ё", "е")
    if not any("а" <= char <= "я" for char in normalized):
        return normalized
    for suffix in _RUSSIAN_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 3:
            return normalized[: -len(suffix)]
    return normalized


def _coverage_content_stems(text: str) -> set[str]:
    stems = {
        _coverage_stem(token)
        for token in _TOKEN_PATTERN.findall(text)
        if token.casefold().replace("ё", "е") not in _RUSSIAN_FUNCTION_WORDS
    }
    # Generic perception verbs ("слышно", "звучит") carry provenance, not
    # claim identity; counting them made unrelated audio claims look covered.
    stems = {stem for stem in stems if not stem.startswith(("слыш", "звуч"))}
    for equivalents in _RUSSIAN_PROVENANCE_EQUIVALENTS:
        stems.difference_update(equivalents)
    return stems


def _claim_coverage(caption: str, request: NarrationRequest) -> dict[str, object]:
    """Map caption text to source IDs conservatively; this is not an entailment model."""
    sources = [(claim.claim_id, claim.text_ru) for claim in request.claims]
    sources.extend((quote.segment_id, quote.text) for quote in request.asr_quotes)
    caption_signature = CaptionDeduplicator.signature(caption)
    caption_segments = [
        segment.strip() for segment in re.split(r"[.!?;:,]+", caption) if segment.strip()
    ] or [caption]
    coverage: list[dict[str, object]] = []
    for source_id, source_text in sources:
        source_signature = CaptionDeduplicator.signature(source_text)
        source_stems = _coverage_content_stems(source_text)
        exact_source_match = bool(
            source_signature and f" {source_signature} " in f" {caption_signature} "
        )
        best_score = 1.0 if exact_source_match else 0.0
        best_segment = source_text if exact_source_match else ""
        if source_stems and not exact_source_match:
            for segment in caption_segments:
                segment_stems = _coverage_content_stems(segment)
                score = len(source_stems.intersection(segment_stems)) / len(source_stems)
                if score > best_score:
                    best_score = score
                    best_segment = segment
        source_has_negation = any(
            token.casefold().replace("ё", "е")
            in {"не", "нет", "без", "ни", "никогда", "никто", "ничто"}
            for token in _TOKEN_PATTERN.findall(source_text)
        )
        segment_has_negation = any(
            token.casefold().replace("ё", "е")
            in {"не", "нет", "без", "ни", "никогда", "никто", "ничто"}
            for token in _TOKEN_PATTERN.findall(best_segment)
        )
        if not source_stems:
            status = "uncertain"
        elif (
            best_score >= _CLAIM_COVERAGE_THRESHOLD and source_has_negation == segment_has_negation
        ):
            status = "expressed"
        elif best_score == 0:
            status = "omitted"
        else:
            status = "uncertain"
        coverage.append(
            {
                "claim_id": source_id,
                "status": status,
                "lexical_coverage": round(best_score, 3),
            }
        )
    expressed = tuple(
        sorted(item["claim_id"] for item in coverage if item["status"] == "expressed")
    )
    omitted = tuple(sorted(item["claim_id"] for item in coverage if item["status"] == "omitted"))
    uncertain = tuple(
        sorted(item["claim_id"] for item in coverage if item["status"] == "uncertain")
    )
    return {
        "input_claim_ids": tuple(sorted(request.source_ids)),
        "expressed_claim_ids": expressed,
        "omitted_claim_ids": omitted,
        "uncertain_claim_ids": uncertain,
        "claim_coverage": tuple(coverage),
    }


def _merge_unique_ids(*groups: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for group in groups for item in group))


@dataclass(frozen=True, slots=True)
class NarrationResponse:
    caption_ru: str
    used_claim_ids: tuple[str, ...]
    start_ms: int
    end_ms: int
    warnings: tuple[str, ...] = ()
    new_unsupported_claims: tuple[str, ...] = ()
    input_claim_ids: tuple[str, ...] = ()
    expressed_claim_ids: tuple[str, ...] = ()
    omitted_claim_ids: tuple[str, ...] = ()
    uncertain_claim_ids: tuple[str, ...] = ()
    claim_coverage: tuple[dict[str, object], ...] = ()
    claim_coverage_method: str = _CLAIM_COVERAGE_METHOD

    def __post_init__(self) -> None:
        if (
            not isinstance(self.caption_ru, str)
            or not self.caption_ru.strip()
            or len(self.caption_ru) > 2000
        ):
            raise ValueError("caption_ru must contain between 1 and 2000 characters")
        if (
            not self.used_claim_ids
            or any(not isinstance(item, str) or not item for item in self.used_claim_ids)
            or len(set(self.used_claim_ids)) != len(self.used_claim_ids)
        ):
            raise ValueError("used_claim_ids must be non-empty and unique")
        if not self.input_claim_ids:
            object.__setattr__(self, "input_claim_ids", tuple(sorted(self.used_claim_ids)))
        if not self.expressed_claim_ids:
            object.__setattr__(self, "expressed_claim_ids", tuple(sorted(self.used_claim_ids)))
        id_groups = (
            self.input_claim_ids,
            self.expressed_claim_ids,
            self.omitted_claim_ids,
            self.uncertain_claim_ids,
        )
        if any(len(group) != len(set(group)) for group in id_groups):
            raise ValueError("claim coverage IDs must be unique")
        if set(self.used_claim_ids) != set(self.expressed_claim_ids):
            raise ValueError("used_claim_ids must match expressed_claim_ids")
        if set(self.input_claim_ids) != (
            set(self.expressed_claim_ids)
            | set(self.omitted_claim_ids)
            | set(self.uncertain_claim_ids)
        ):
            raise ValueError("claim coverage statuses must partition input_claim_ids")
        if not self.claim_coverage:
            object.__setattr__(
                self,
                "claim_coverage",
                tuple(
                    {
                        "claim_id": claim_id,
                        "status": "expressed",
                        "lexical_coverage": 1.0,
                    }
                    for claim_id in self.expressed_claim_ids
                ),
            )
        if {item.get("claim_id") for item in self.claim_coverage} != set(self.input_claim_ids):
            raise ValueError("claim_coverage must include every input claim ID")
        if (
            type(self.start_ms) is not int
            or type(self.end_ms) is not int
            or self.start_ms < 0
            or self.end_ms <= self.start_ms
        ):
            raise ValueError("caption interval must satisfy 0 <= start_ms < end_ms")
        if len(self.warnings) > 8 or any(
            not isinstance(item, str) or len(item) > 500 for item in self.warnings
        ):
            raise ValueError("warnings must contain at most eight strings up to 500 characters")

    def to_dict(self) -> dict[str, object]:
        return {
            "caption_ru": self.caption_ru,
            "used_claim_ids": list(self.used_claim_ids),
            "input_claim_ids": list(self.input_claim_ids),
            "expressed_claim_ids": list(self.expressed_claim_ids),
            "omitted_claim_ids": list(self.omitted_claim_ids),
            "uncertain_claim_ids": list(self.uncertain_claim_ids),
            "claim_coverage": [dict(item) for item in self.claim_coverage],
            "claim_coverage_method": self.claim_coverage_method,
            "new_unsupported_claims": list(self.new_unsupported_claims),
            "time_range": {"start_ms": self.start_ms, "end_ms": self.end_ms},
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class NarrationResult:
    response: NarrationResponse
    status: Literal["generated", "fallback"]
    model_revision: str
    prompt_version: str
    event_revisions: tuple[NarrationEventRef, ...]
    latency_ms: float
    backend: Literal["qwen", "template"] = "qwen"
    generated_token_count: int | None = None
    generation_ms: float | None = None
    generation_tokens_per_second: float | None = None

    def __post_init__(self) -> None:
        if not self.model_revision or not self.prompt_version:
            raise ValueError("model_revision and prompt_version are required")
        if self.status not in {"generated", "fallback"}:
            raise ValueError("unsupported narration status")
        if self.backend not in {"qwen", "template"}:
            raise ValueError("unsupported narration backend")
        if not self.event_revisions or len({item.event_id for item in self.event_revisions}) != len(
            self.event_revisions
        ):
            raise ValueError("event revisions must be present and unique")
        if (
            isinstance(self.latency_ms, bool)
            or not isinstance(self.latency_ms, (int, float))
            or not math.isfinite(self.latency_ms)
            or self.latency_ms < 0
        ):
            raise ValueError("latency_ms must be a finite non-negative number")
        if self.generated_token_count is not None and (
            type(self.generated_token_count) is not int or self.generated_token_count < 0
        ):
            raise ValueError("generated_token_count must be a non-negative integer or None")
        if self.generation_ms is not None and (
            isinstance(self.generation_ms, bool)
            or not isinstance(self.generation_ms, (int, float))
            or not math.isfinite(self.generation_ms)
            or self.generation_ms < 0
        ):
            raise ValueError("generation_ms must be finite and non-negative or None")
        if self.generation_tokens_per_second is not None and (
            isinstance(self.generation_tokens_per_second, bool)
            or not isinstance(self.generation_tokens_per_second, (int, float))
            or not math.isfinite(self.generation_tokens_per_second)
            or self.generation_tokens_per_second < 0
        ):
            raise ValueError("generation_tokens_per_second must be finite and non-negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "record_type": "caption",
            **self.response.to_dict(),
            "status": self.status,
            "backend": self.backend,
            "model_revision": self.model_revision,
            "prompt_version": self.prompt_version,
            "event_revisions": [asdict(item) for item in self.event_revisions],
            "latency_ms": self.latency_ms,
            "generated_token_count": self.generated_token_count,
            "generation_ms": self.generation_ms,
            "tokens_per_second": round(self.generation_tokens_per_second, 3)
            if self.generation_tokens_per_second is not None
            else round(self.generated_token_count / (self.generation_ms / 1000), 3)
            if self.generated_token_count is not None
            and self.generation_ms is not None
            and self.generation_ms > 0
            else None,
        }


@dataclass(slots=True)
class _CaptionGroup:
    start_ms: int
    end_ms: int
    used_claim_ids: tuple[str, ...]
    event_revisions: tuple[NarrationEventRef, ...]
    caption_ru: str | None = None
    input_claim_ids: tuple[str, ...] = ()
    expressed_claim_ids: tuple[str, ...] = ()
    omitted_claim_ids: tuple[str, ...] = ()
    uncertain_claim_ids: tuple[str, ...] = ()
    claim_coverage: tuple[dict[str, object], ...] = ()


def _merge_group_coverage(group: _CaptionGroup, coverage: dict[str, object]) -> None:
    group.input_claim_ids = _merge_unique_ids(
        group.input_claim_ids,
        cast(tuple[str, ...], coverage["input_claim_ids"]),
    )
    group.expressed_claim_ids = _merge_unique_ids(
        group.expressed_claim_ids,
        cast(tuple[str, ...], coverage["expressed_claim_ids"]),
    )
    group.omitted_claim_ids = _merge_unique_ids(
        group.omitted_claim_ids,
        cast(tuple[str, ...], coverage["omitted_claim_ids"]),
    )
    group.uncertain_claim_ids = _merge_unique_ids(
        group.uncertain_claim_ids,
        cast(tuple[str, ...], coverage["uncertain_claim_ids"]),
    )
    by_id = {str(item["claim_id"]): item for item in group.claim_coverage}
    coverage_rows = cast(tuple[dict[str, object], ...], coverage["claim_coverage"])
    by_id.update({str(item["claim_id"]): item for item in coverage_rows})
    group.claim_coverage = tuple(by_id.values())
    group.used_claim_ids = group.expressed_claim_ids


class CaptionDeduplicator:
    """Collapse identical nearby captions while retaining their source revisions."""

    def __init__(self, *, max_gap_ms: int = 5_000, capacity: int = 256) -> None:
        if max_gap_ms < 0 or capacity < 1:
            raise ValueError("caption deduplication bounds must be non-negative and positive")
        self.max_gap_ms = max_gap_ms
        self.capacity = capacity
        self._groups: OrderedDict[str, _CaptionGroup] = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def signature(caption: str) -> str:
        return " ".join(
            token.casefold().replace("ё", "е") for token in _TOKEN_PATTERN.findall(caption)
        )

    def process(self, result: NarrationResult) -> dict[str, object]:
        """Return a caption row or a visible duplicate row for adjacent repeated text."""
        record = result.to_dict()
        response = result.response
        signature = self.signature(response.caption_ru)
        with self._lock:
            previous = self._groups.get(signature)
            if previous is not None:
                previous_range = {"start_ms": previous.start_ms, "end_ms": previous.end_ms}
                adjacent = (
                    response.start_ms <= previous.end_ms + self.max_gap_ms
                    and response.end_ms >= previous.start_ms - self.max_gap_ms
                )
                if adjacent:
                    revisions = {item.event_id: item for item in previous.event_revisions}
                    for item in result.event_revisions:
                        existing = revisions.get(item.event_id)
                        if existing is None or item.revision > existing.revision:
                            revisions[item.event_id] = item
                    previous.start_ms = min(previous.start_ms, response.start_ms)
                    previous.end_ms = max(previous.end_ms, response.end_ms)
                    previous.used_claim_ids = tuple(
                        dict.fromkeys((*previous.used_claim_ids, *response.used_claim_ids))
                    )
                    _merge_group_coverage(
                        previous,
                        {
                            "input_claim_ids": response.input_claim_ids,
                            "expressed_claim_ids": response.expressed_claim_ids,
                            "omitted_claim_ids": response.omitted_claim_ids,
                            "uncertain_claim_ids": response.uncertain_claim_ids,
                            "claim_coverage": response.claim_coverage,
                        },
                    )
                    previous.event_revisions = tuple(revisions.values())
                    self._groups.move_to_end(signature)
                    record["record_type"] = "caption_deduplicated"
                    record["deduplication"] = {
                        "reason": "same_caption_in_adjacent_time_range",
                        "previous_time_range": previous_range,
                        "covered_time_range": {
                            "start_ms": previous.start_ms,
                            "end_ms": previous.end_ms,
                        },
                        "covered_used_claim_ids": list(previous.used_claim_ids),
                        "covered_input_claim_ids": list(previous.input_claim_ids),
                        "covered_expressed_claim_ids": list(previous.expressed_claim_ids),
                        "covered_omitted_claim_ids": list(previous.omitted_claim_ids),
                        "covered_uncertain_claim_ids": list(previous.uncertain_claim_ids),
                        "covered_claim_coverage": [dict(item) for item in previous.claim_coverage],
                        "covered_event_revisions": [
                            asdict(item) for item in previous.event_revisions
                        ],
                    }
                    return record
            self._groups[signature] = _CaptionGroup(
                start_ms=response.start_ms,
                end_ms=response.end_ms,
                used_claim_ids=response.used_claim_ids,
                event_revisions=result.event_revisions,
                input_claim_ids=response.input_claim_ids,
                expressed_claim_ids=response.expressed_claim_ids,
                omitted_claim_ids=response.omitted_claim_ids,
                uncertain_claim_ids=response.uncertain_claim_ids,
                claim_coverage=response.claim_coverage,
            )
            while len(self._groups) > self.capacity:
                self._groups.popitem(last=False)
        return record


class NarrationRequestDeduplicator:
    """Skip nearby Qwen calls when their complete factual inputs are identical."""

    def __init__(self, *, max_gap_ms: int = 5_000, capacity: int = 256) -> None:
        if max_gap_ms < 0 or capacity < 1:
            raise ValueError("narration deduplication bounds must be non-negative and positive")
        self.max_gap_ms = max_gap_ms
        self.capacity = capacity
        self._groups: OrderedDict[str, _CaptionGroup] = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def signature(request: NarrationRequest) -> str:
        payload = {
            "claims": sorted(
                {CaptionDeduplicator.signature(item.text_ru) for item in request.claims}
            ),
            "asr_quotes": sorted(
                {CaptionDeduplicator.signature(item.text) for item in request.asr_quotes}
            ),
            "state": request.state,
            "delta": request.delta,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def should_skip(self, request: NarrationRequest) -> dict[str, object] | None:
        signature = self.signature(request)
        start_ms, end_ms = request.time_range
        with self._lock:
            previous = self._groups.get(signature)
            if previous is None or previous.caption_ru is None:
                return None
            previous_range = {"start_ms": previous.start_ms, "end_ms": previous.end_ms}
            if not (
                start_ms <= previous.end_ms + self.max_gap_ms
                and end_ms >= previous.start_ms - self.max_gap_ms
            ):
                return None
            coverage = _claim_coverage(previous.caption_ru, request)
            revisions = {item.event_id: item for item in previous.event_revisions}
            for item in request.event_refs:
                existing = revisions.get(item.event_id)
                if existing is None or item.revision > existing.revision:
                    revisions[item.event_id] = item
            previous.start_ms = min(previous.start_ms, start_ms)
            previous.end_ms = max(previous.end_ms, end_ms)
            _merge_group_coverage(previous, coverage)
            previous.event_revisions = tuple(revisions.values())
            self._groups.move_to_end(signature)
            return {
                "schema_version": 1,
                "record_type": "narration_deduplicated",
                "level": "L3",
                "reason": "identical_accepted_sources_in_adjacent_time_range",
                "caption_ru": previous.caption_ru,
                "time_range": {"start_ms": start_ms, "end_ms": end_ms},
                "previous_time_range": previous_range,
                "covered_time_range": {
                    "start_ms": previous.start_ms,
                    "end_ms": previous.end_ms,
                },
                "covered_claim_ids": list(previous.used_claim_ids),
                "input_claim_ids": list(coverage["input_claim_ids"]),
                "expressed_claim_ids": list(coverage["expressed_claim_ids"]),
                "omitted_claim_ids": list(coverage["omitted_claim_ids"]),
                "uncertain_claim_ids": list(coverage["uncertain_claim_ids"]),
                "claim_coverage": [
                    dict(item)
                    for item in cast(tuple[dict[str, object], ...], coverage["claim_coverage"])
                ],
                "covered_input_claim_ids": list(previous.input_claim_ids),
                "covered_expressed_claim_ids": list(previous.expressed_claim_ids),
                "covered_omitted_claim_ids": list(previous.omitted_claim_ids),
                "covered_uncertain_claim_ids": list(previous.uncertain_claim_ids),
                "covered_event_revisions": [asdict(item) for item in previous.event_revisions],
            }

    def remember(self, request: NarrationRequest, *, caption_ru: str | None = None) -> None:
        signature = self.signature(request)
        start_ms, end_ms = request.time_range
        with self._lock:
            previous = self._groups.get(signature)
            if previous is not None and (
                start_ms <= previous.end_ms + self.max_gap_ms
                and end_ms >= previous.start_ms - self.max_gap_ms
            ):
                previous.start_ms = min(previous.start_ms, start_ms)
                previous.end_ms = max(previous.end_ms, end_ms)
                selected_caption = previous.caption_ru or caption_ru
                if selected_caption is not None:
                    _merge_group_coverage(previous, _claim_coverage(selected_caption, request))
                revisions = {item.event_id: item for item in previous.event_revisions}
                revisions.update({item.event_id: item for item in request.event_refs})
                previous.event_revisions = tuple(revisions.values())
                if previous.caption_ru is None:
                    previous.caption_ru = caption_ru
                self._groups.move_to_end(signature)
            else:
                self._groups[signature] = _CaptionGroup(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    used_claim_ids=(),
                    event_revisions=request.event_refs,
                    caption_ru=caption_ru,
                )
                if caption_ru is not None:
                    _merge_group_coverage(
                        self._groups[signature], _claim_coverage(caption_ru, request)
                    )
            while len(self._groups) > self.capacity:
                self._groups.popitem(last=False)


class QwenNarrator:
    """Run one bounded, non-thinking Qwen turn through the pinned llama.cpp CLI."""

    def __init__(
        self,
        model: dict[str, Any],
        models_dir: Path,
        repo_root: Path,
        *,
        threads: int = 4,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_input_chars: int = DEFAULT_MAX_INPUT_CHARS,
    ) -> None:
        if threads < 1:
            raise ValueError("threads must be positive")
        if not 16 <= max_tokens <= 256:
            raise ValueError("max_tokens must be between 16 and 256")
        if not 1.0 <= timeout_seconds <= 120.0:
            raise ValueError("timeout_seconds must be between 1 and 120")
        if not 256 <= max_input_chars <= DEFAULT_MAX_INPUT_CHARS:
            raise ValueError(f"max_input_chars must be between 256 and {DEFAULT_MAX_INPUT_CHARS}")
        self.model = model
        self.model_revision = str(model["revision"])
        verified_files = verify_local_artifacts("qwen3_0_6b", model, models_dir)
        self.model_path = models_dir / "qwen3_0_6b" / str(model["file"])
        self.llama_cli = models_dir / "runtimes" / "llama_cpp" / "b11886" / "bin" / "llama-cli.exe"
        if str(self.llama_cli) not in verified_files and not self.llama_cli.is_file():
            raise FileNotFoundError(
                f"llama.cpp executable is missing: {self.llama_cli}; "
                "fetch it with scripts/download_models.py --runtime llama_cpp"
            )
        self.prompt_path = repo_root / "configs" / "prompts" / "narrator_ru_v2.jinja"
        self.schema_path = repo_root / "configs" / "schemas" / "narration_v1.schema.json"
        self.template_path = repo_root / "configs" / "qwen3_nonthinking.jinja"
        for path in (self.prompt_path, self.schema_path, self.template_path):
            if not path.is_file():
                raise FileNotFoundError(f"narrator resource is missing: {path}")
        self.threads = threads
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.max_input_chars = max_input_chars

    def _build_prompt(self, request: NarrationRequest) -> str:
        facts = json.dumps(request.facts_payload(), ensure_ascii=False, sort_keys=True)
        template = self.prompt_path.read_text(encoding="utf-8")
        prompt = template.replace("{{facts_json}}", facts)
        if "{{facts_json}}" in prompt:
            raise ValueError("narrator prompt template contains an unresolved placeholder")
        if len(prompt) > self.max_input_chars:
            raise ValueError(
                f"narration chunk is {len(prompt)} characters; limit is {self.max_input_chars}"
            )
        return prompt

    def _command(self, prompt: str, output_path: Path) -> list[str]:
        return [
            str(self.llama_cli),
            "--model",
            str(self.model_path),
            "--prompt",
            prompt,
            "--chat-template-file",
            str(self.template_path),
            "--jinja",
            "--single-turn",
            "--no-display-prompt",
            "--simple-io",
            "--perf",
            "--show-timings",
            "--output-file",
            str(output_path),
            "--threads",
            str(self.threads),
            "--ctx-size",
            "2048",
            "--predict",
            str(self.max_tokens),
            "--temp",
            "0",
            "--top-k",
            "1",
            "--seed",
            "7",
        ]

    @staticmethod
    def _extract_caption(output: str) -> str:
        text = output
        assistant_markers = list(re.finditer(r"(?:^|\n)Assistant:\s*", text, re.IGNORECASE))
        if assistant_markers:
            text = text[assistant_markers[-1].end() :]
        elif "\nUser:" in text or "\nAssistant:" in text:
            raise ValueError("Qwen transcript did not contain an assistant answer")
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.split(r"\r?\n\s*(?:\[ Prompt:|Exiting\.\.\.)", text, maxsplit=1)[0]
        text = text.strip().strip("`\"'").strip()
        if (
            not text
            or len(text) > 2000
            or "<think>" in text
            or "```" in text
            or not any("\u0400" <= char <= "\u04ff" for char in text)
        ):
            raise ValueError("Qwen output is not a short Russian caption")
        return text

    @staticmethod
    def _parse_generation_metrics(
        output: str,
    ) -> tuple[int | None, float | None, float | None]:
        """Read generated-token throughput and, when present, count and duration."""
        match = re.search(
            r"(?:eval|generation) time\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*ms\s*/\s*"
            r"([0-9]+)\s*tokens\b",
            output,
            flags=re.IGNORECASE,
        )
        if match is not None:
            generated_tokens = int(match.group(2))
            generation_ms = float(match.group(1))
            return (
                generated_tokens,
                generation_ms,
                round(generated_tokens / (generation_ms / 1000), 3) if generation_ms > 0 else None,
            )
        rate_match = re.search(
            r"Generation:\s*([0-9]+(?:\.[0-9]+)?)\s*t/s",
            output,
            flags=re.IGNORECASE,
        )
        return None, None, float(rate_match.group(1)) if rate_match is not None else None

    @staticmethod
    def _unsupported_relationship_statements(
        caption: str,
        request: NarrationRequest,
    ) -> tuple[str, ...]:
        """Flag clauses whose content words cannot be grounded in one source claim."""
        source_texts = [claim.text_ru for claim in request.claims]
        source_texts.extend(quote.text for quote in request.asr_quotes)
        source_stems = [stems for text in source_texts if (stems := _coverage_content_stems(text))]
        if not source_stems:
            return ("<unsupported_relation>",)
        clauses = re.split(
            r"[.!?;:,]+|\b(?:а|и|но|однако|затем|пока)\b",
            caption,
            flags=re.IGNORECASE,
        )
        for clause in clauses:
            generated_stems = _coverage_content_stems(clause)
            if not generated_stems:
                continue
            best_precision = max(
                len(generated_stems.intersection(source)) / len(generated_stems)
                for source in source_stems
            )
            if best_precision < _CLAIM_COVERAGE_THRESHOLD:
                return ("<unsupported_relation>",)
        return ()

    @staticmethod
    def _unsupported_provenance_terms(caption: str, request: NarrationRequest) -> tuple[str, ...]:
        """List generated words and polarity changes not traceable to accepted sources."""
        accepted_sources = cast(list[dict[str, object]], request.facts_payload()["accepted_claims"])
        source_text = [str(claim["text_ru"]) for claim in accepted_sources]
        source_text.extend(quote.text for quote in request.asr_quotes)

        def normalize(token: str) -> str:
            return token.casefold().replace("ё", "е")

        def stem(token: str) -> str:
            normalized = normalize(token)
            if not any("а" <= char <= "я" for char in normalized):
                return normalized
            for suffix in _RUSSIAN_SUFFIXES:
                if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 3:
                    return normalized[: -len(suffix)]
            return normalized

        supported_stems = {
            stem(token) for text in source_text for token in _TOKEN_PATTERN.findall(text)
        }
        for equivalents in _RUSSIAN_PROVENANCE_EQUIVALENTS:
            if supported_stems.intersection(equivalents):
                supported_stems.update(equivalents)
        negation = {"не", "нет", "без", "ни", "никогда", "никто", "ничто"}
        unsupported: set[str] = set()
        generated_tokens = _TOKEN_PATTERN.findall(caption)
        for token in generated_tokens:
            normalized = normalize(token)
            if normalized in negation or normalized in _RUSSIAN_FUNCTION_WORDS:
                continue
            if stem(token) not in supported_stems:
                unsupported.add(normalized)
        source_negations = sum(
            normalize(token) in negation
            for text in source_text
            for token in _TOKEN_PATTERN.findall(text)
        )
        generated_negations = sum(normalize(token) in negation for token in generated_tokens)
        if generated_negations > source_negations:
            unsupported.add("<negation_mismatch>")
        generated_segments = re.split(r"[.!?;:,]+", caption)
        for text in source_text:
            for source_segment in re.split(r"[.!?;:,]+", text):
                source_tokens = _TOKEN_PATTERN.findall(source_segment)
                if not any(normalize(token) in negation for token in source_tokens):
                    continue
                negated_stems = {
                    stem(token)
                    for token in source_tokens
                    if normalize(token) not in negation
                    and normalize(token) not in _RUSSIAN_FUNCTION_WORDS
                }
                if not negated_stems:
                    continue
                for generated_segment in generated_segments:
                    generated_segment_tokens = _TOKEN_PATTERN.findall(generated_segment)
                    generated_stems = {stem(token) for token in generated_segment_tokens}
                    if not negated_stems.intersection(generated_stems):
                        continue
                    if not any(normalize(token) in negation for token in generated_segment_tokens):
                        unsupported.add("<negation_mismatch>")
                        break
        if not generated_tokens:
            unsupported.add("<empty_caption>")
        unsupported.update(QwenNarrator._unsupported_relationship_statements(caption, request))
        return tuple(sorted(unsupported))

    @staticmethod
    def _has_supported_vocabulary(caption: str, request: NarrationRequest) -> bool:
        """Compatibility wrapper for the stricter source-provenance check."""
        return not QwenNarrator._unsupported_provenance_terms(caption, request)

    @staticmethod
    def _fallback(
        request: NarrationRequest,
        warning: str,
        *,
        unsupported_terms: tuple[str, ...] = (),
    ) -> NarrationResponse:
        accepted_sources = cast(list[dict[str, object]], request.facts_payload()["accepted_claims"])
        texts = [str(claim["text_ru"]).strip() for claim in accepted_sources]
        texts.extend(f"Цитата: «{quote.text.strip()}»" for quote in request.asr_quotes)
        input_claim_ids = tuple(sorted(request.source_ids))
        coverage = _claim_coverage(" ".join(texts), request)
        coverage["expressed_claim_ids"] = input_claim_ids
        coverage["omitted_claim_ids"] = ()
        coverage["uncertain_claim_ids"] = ()
        coverage["claim_coverage"] = tuple(
            {
                "claim_id": claim_id,
                "status": "expressed",
                "lexical_coverage": 1.0,
            }
            for claim_id in input_claim_ids
        )
        return NarrationResponse(
            caption_ru=" ".join(texts),
            used_claim_ids=input_claim_ids,
            start_ms=request.time_range[0],
            end_ms=request.time_range[1],
            warnings=(warning,),
            new_unsupported_claims=unsupported_terms,
            input_claim_ids=input_claim_ids,
            expressed_claim_ids=input_claim_ids,
            omitted_claim_ids=(),
            uncertain_claim_ids=(),
            claim_coverage=cast(tuple[dict[str, object], ...], coverage["claim_coverage"]),
        )

    def narrate(self, request: NarrationRequest) -> NarrationResult:
        """Generate a caption; timeouts and invalid output use a source-only fallback."""
        prompt = self._build_prompt(request)
        started = time.perf_counter()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as output_file:
            output_path = Path(output_file.name)
        status: Literal["generated", "fallback"] = "fallback"
        generated_token_count: int | None = None
        generation_ms: float | None = None
        generation_tokens_per_second: float | None = None
        try:
            completed = subprocess.run(
                self._command(prompt, output_path),
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
            output_chunks = []
            for output in (completed.stdout, completed.stderr):
                if isinstance(output, bytes):
                    output_chunks.append(output.decode("utf-8", errors="replace"))
                elif isinstance(output, str):
                    output_chunks.append(output)
            (
                generated_token_count,
                generation_ms,
                generation_tokens_per_second,
            ) = self._parse_generation_metrics("\n".join(output_chunks))
            caption = self._extract_caption(output_path.read_text(encoding="utf-8"))
            unsupported_terms = self._unsupported_provenance_terms(caption, request)
            if unsupported_terms:
                response = self._fallback(
                    request,
                    "unsupported_terms",
                    unsupported_terms=unsupported_terms,
                )
                status = "fallback"
            else:
                coverage = _claim_coverage(caption, request)
                expressed_claim_ids = cast(tuple[str, ...], coverage["expressed_claim_ids"])
                if not expressed_claim_ids:
                    response = self._fallback(request, "claim_mapping_uncertain")
                    status = "fallback"
                else:
                    response = NarrationResponse(
                        caption_ru=caption,
                        used_claim_ids=expressed_claim_ids,
                        start_ms=request.time_range[0],
                        end_ms=request.time_range[1],
                        input_claim_ids=cast(tuple[str, ...], coverage["input_claim_ids"]),
                        expressed_claim_ids=expressed_claim_ids,
                        omitted_claim_ids=cast(tuple[str, ...], coverage["omitted_claim_ids"]),
                        uncertain_claim_ids=cast(tuple[str, ...], coverage["uncertain_claim_ids"]),
                        claim_coverage=cast(
                            tuple[dict[str, object], ...], coverage["claim_coverage"]
                        ),
                    )
                    status = "generated"
        except subprocess.TimeoutExpired:
            response = self._fallback(request, "qwen_timeout")
            status = "fallback"
        except (OSError, subprocess.CalledProcessError, ValueError):
            response = self._fallback(request, "qwen_output_invalid")
            status = "fallback"
        finally:
            output_path.unlink(missing_ok=True)
        latency_ms = (time.perf_counter() - started) * 1000
        return NarrationResult(
            response=response,
            status=status,
            model_revision=self.model_revision,
            prompt_version=PROMPT_VERSION,
            event_revisions=request.event_refs,
            latency_ms=round(latency_ms, 3),
            backend="qwen",
            generated_token_count=generated_token_count,
            generation_ms=generation_ms,
            generation_tokens_per_second=generation_tokens_per_second,
        )


class TemplateNarrator:
    """Source-only caption baseline with no model load or generated facts."""

    model_revision = "template-source-only-v1"
    prompt_version = "template-source-only-v1"

    def narrate(self, request: NarrationRequest) -> NarrationResult:
        started = time.perf_counter()
        response = QwenNarrator._fallback(request, "template_baseline")
        return NarrationResult(
            response=response,
            status="fallback",
            model_revision=self.model_revision,
            prompt_version=self.prompt_version,
            event_revisions=request.event_refs,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            backend="template",
        )
