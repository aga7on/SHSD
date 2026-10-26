"""Validated, versioned natural-language candidate profiles."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from shsd.embeddings.provider import EmbeddingProvider, EmbeddingRecord


@dataclass(frozen=True, slots=True)
class HypothesisCandidate:
    candidate_id: str
    text_en: str
    text_ru: str
    polarity: str
    opposes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HypothesisAxis:
    axis_id: str
    modality: str
    mutually_exclusive: bool
    candidates: tuple[HypothesisCandidate, ...]


@dataclass(frozen=True, slots=True)
class HypothesisProfile:
    profile_id: str
    profile_version: int
    model_revision: str
    embedding_language: str
    display_language: str
    axes: tuple[HypothesisAxis, ...]
    unknown_id: str = "unknown"

    def iter_candidates(self) -> Iterator[tuple[HypothesisAxis, HypothesisCandidate]]:
        for axis in self.axes:
            for candidate in axis.candidates:
                yield axis, candidate

    def candidate_fingerprint(self) -> str:
        payload = {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "model_revision": self.model_revision,
            "embedding_language": self.embedding_language,
            "display_language": self.display_language,
            "unknown_id": self.unknown_id,
            "axes": [
                {
                    "axis_id": axis.axis_id,
                    "modality": axis.modality,
                    "mutually_exclusive": axis.mutually_exclusive,
                    "candidate_id": candidate.candidate_id,
                    "text_en": candidate.text_en,
                    "text_ru": candidate.text_ru,
                    "polarity": candidate.polarity,
                    "opposes": candidate.opposes,
                }
                for axis, candidate in self.iter_candidates()
            ],
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()


def encode_profile_candidates(
    profile: HypothesisProfile, provider: EmbeddingProvider
) -> dict[str, dict[str, EmbeddingRecord]]:
    """Encode one profile's text bank under its content fingerprint namespace."""
    entries = list(profile.iter_candidates())
    fingerprint = f"{profile.profile_id}:{profile.candidate_fingerprint()}"
    records = provider.encode_texts(
        [candidate.text_en for _, candidate in entries],
        cache_namespace=fingerprint,
    )
    if len(records) != len(entries):
        raise RuntimeError("embedding provider returned the wrong candidate vector count")
    result: dict[str, dict[str, EmbeddingRecord]] = {}
    for (axis, candidate), record in zip(entries, records, strict=True):
        if record.model_revision != profile.model_revision:
            raise ValueError(
                f"candidate profile {profile.profile_id} uses {profile.model_revision}, "
                f"but provider returned {record.model_revision}"
            )
        result.setdefault(axis.axis_id, {})[candidate.candidate_id] = record
    return result


def _required_string(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: {key} must be a non-empty string")
    return value.strip()


def _load_profile(path: Path, *, expected_model_revision: str | None) -> HypothesisProfile:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError(f"{path}: unsupported hypothesis profile schema")
    profile_id = _required_string(raw, "profile_id", str(path))
    model_revision = _required_string(raw, "model_revision", str(path))
    if expected_model_revision is not None and model_revision != expected_model_revision:
        raise ValueError(
            f"{path}: profile model revision {model_revision} does not match "
            f"loaded model revision {expected_model_revision}"
        )
    profile_version = raw.get("profile_version")
    if not isinstance(profile_version, int) or profile_version < 1:
        raise ValueError(f"{path}: profile_version must be a positive integer")

    unknown = raw.get("unknown")
    if not isinstance(unknown, dict) or unknown.get("embedding") is not False:
        raise ValueError(f"{path}: unknown must be a non-embedded abstention")
    unknown_id = _required_string(cast(dict[str, Any], unknown), "id", str(path))
    if unknown.get("decision") != "uncertain":
        raise ValueError(f"{path}: unknown decision must be uncertain")

    raw_axes = raw.get("axes")
    if not isinstance(raw_axes, dict) or not raw_axes:
        raise ValueError(f"{path}: axes must be a non-empty mapping")
    axes: list[HypothesisAxis] = []
    for axis_id, axis_raw in raw_axes.items():
        if not isinstance(axis_id, str) or not axis_id.strip() or not isinstance(axis_raw, dict):
            raise ValueError(f"{path}: every axis must have an id and mapping")
        modality = _required_string(axis_raw, "modality", f"{path}:{axis_id}")
        mutually_exclusive = axis_raw.get("mutually_exclusive")
        if not isinstance(mutually_exclusive, bool):
            raise ValueError(f"{path}:{axis_id}: mutually_exclusive must be boolean")
        raw_candidates = axis_raw.get("candidates")
        if not isinstance(raw_candidates, list) or len(raw_candidates) < 2:
            raise ValueError(f"{path}:{axis_id}: at least two candidates are required")
        candidates: list[HypothesisCandidate] = []
        for candidate_raw in raw_candidates:
            if not isinstance(candidate_raw, dict):
                raise ValueError(f"{path}:{axis_id}: candidate must be a mapping")
            candidate_id = _required_string(candidate_raw, "id", f"{path}:{axis_id}")
            text_en = _required_string(candidate_raw, "text_en", f"{path}:{axis_id}")
            text_ru = _required_string(candidate_raw, "text_ru", f"{path}:{axis_id}")
            polarity = _required_string(candidate_raw, "polarity", f"{path}:{axis_id}")
            if polarity not in {"positive", "negative"}:
                raise ValueError(f"{path}:{axis_id}:{candidate_id}: invalid polarity")
            opposes_raw = candidate_raw.get("opposes")
            if not isinstance(opposes_raw, list) or not all(
                isinstance(item, str) for item in opposes_raw
            ):
                raise ValueError(f"{path}:{axis_id}:{candidate_id}: opposes must be a string list")
            candidates.append(
                HypothesisCandidate(
                    candidate_id=candidate_id,
                    text_en=text_en,
                    text_ru=text_ru,
                    polarity=polarity,
                    opposes=tuple(opposes_raw),
                )
            )
        candidate_ids = {item.candidate_id for item in candidates}
        if len(candidate_ids) != len(candidates) or unknown_id in candidate_ids:
            raise ValueError(f"{path}:{axis_id}: candidate ids must be unique and exclude unknown")
        if any(
            opposed_id not in candidate_ids
            for item in candidates
            for opposed_id in item.opposes
        ):
            raise ValueError(f"{path}:{axis_id}: opposes references an unknown candidate id")
        axes.append(
            HypothesisAxis(
                axis_id=axis_id,
                modality=modality,
                mutually_exclusive=mutually_exclusive,
                candidates=tuple(candidates),
            )
        )
    return HypothesisProfile(
        profile_id=profile_id,
        profile_version=profile_version,
        model_revision=model_revision,
        embedding_language=_required_string(raw, "embedding_language", str(path)),
        display_language=_required_string(raw, "display_language", str(path)),
        axes=tuple(axes),
        unknown_id=unknown_id,
    )


def load_profiles(
    directory: Path, *, expected_model_revision: str | None = None
) -> tuple[HypothesisProfile, ...]:
    """Load every YAML profile in stable filename order and validate its model pin."""
    paths = sorted(directory.glob("*.yaml"))
    if not paths:
        raise FileNotFoundError(f"No hypothesis profiles found under {directory}")
    profiles = tuple(
        _load_profile(path, expected_model_revision=expected_model_revision) for path in paths
    )
    profile_ids = [profile.profile_id for profile in profiles]
    if len(set(profile_ids)) != len(profile_ids):
        raise ValueError("hypothesis profile ids must be unique")
    return profiles
