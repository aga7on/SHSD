"""PTS-preserving adapter from production encoder outputs to bridge batches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np

if TYPE_CHECKING:
    from shsd.embeddings.provider import SequenceFeatureRecord

BridgeMode = Literal["IMAGE", "VIDEO", "AUDIO", "AV"]


@dataclass(frozen=True, slots=True)
class TokenSequence:
    """One unpooled encoder sequence with its active mask and model provenance."""

    embeddings: np.ndarray
    attention_mask: np.ndarray
    input_token_ids: np.ndarray | None
    model_revision: str
    preprocess_version: str

    @classmethod
    def from_record(cls, record: SequenceFeatureRecord) -> TokenSequence:
        embeddings = np.asarray(record.token_embeddings)
        attention_mask = np.asarray(record.attention_mask)
        token_ids = None if record.input_token_ids is None else np.asarray(record.input_token_ids)
        if embeddings.ndim != 2 or embeddings.shape[0] == 0 or embeddings.shape[1] == 0:
            raise ValueError(
                "encoder tokens must have shape [tokens, features] with non-zero sizes"
            )
        if not np.isfinite(embeddings).all():
            raise ValueError("encoder tokens must be finite")
        if attention_mask.shape != (embeddings.shape[0],):
            raise ValueError("attention_mask must have one entry per token")
        if not np.issubdtype(attention_mask.dtype, np.bool_):
            raise ValueError("attention_mask must use a boolean dtype")
        if not bool(attention_mask.any()):
            raise ValueError("encoder sequence must contain at least one active token")
        if token_ids is not None and token_ids.shape != (embeddings.shape[0],):
            raise ValueError("input_token_ids must have one entry per token")
        if not record.model_revision or not record.input_preprocess_version:
            raise ValueError("encoder model and preprocessing provenance are required")
        return cls(
            embeddings=embeddings,
            attention_mask=attention_mask,
            input_token_ids=token_ids,
            model_revision=record.model_revision,
            preprocess_version=record.input_preprocess_version,
        )


@dataclass(frozen=True, slots=True)
class FrameFeatures:
    """Feature sequence for exactly one image frame at a source PTS."""

    pts_ms: int
    tokens: TokenSequence

    @classmethod
    def from_record(cls, record: SequenceFeatureRecord) -> FrameFeatures:
        if record.modality != "image" or len(record.frame_pts_ms) != 1:
            raise ValueError(
                "frame features require one IMAGE sequence with exactly one source PTS"
            )
        pts_ms = record.frame_pts_ms[0]
        if record.interval_ms != (pts_ms, pts_ms + 1):
            raise ValueError("IMAGE feature interval must identify its source PTS")
        return cls(pts_ms=pts_ms, tokens=TokenSequence.from_record(record))


@dataclass(frozen=True, slots=True)
class AudioFeatures:
    """Feature sequence for an audio interval; token-level PTS are not implied."""

    start_ms: int
    end_ms: int
    tokens: TokenSequence

    @classmethod
    def from_record(cls, record: SequenceFeatureRecord) -> AudioFeatures:
        if record.modality != "audio" or record.interval_ms is None:
            raise ValueError("audio features require an AUDIO sequence with a source interval")
        start_ms, end_ms = record.interval_ms
        if start_ms < 0 or end_ms <= start_ms:
            raise ValueError("audio interval must satisfy 0 <= start_ms < end_ms")
        return cls(
            start_ms=start_ms,
            end_ms=end_ms,
            tokens=TokenSequence.from_record(record),
        )


@dataclass(frozen=True, slots=True)
class AVFeatureBatch:
    """Ragged per-frame vision plus interval audio, retaining exact source timing."""

    mode: BridgeMode
    source_id: str
    epoch: int
    start_ms: int
    end_ms: int
    frames: tuple[FrameFeatures, ...] = ()
    audio: AudioFeatures | None = None

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("source_id must be non-empty")
        if self.epoch < 0 or self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("invalid epoch or source interval")
        if not isinstance(self.mode, str) or self.mode not in {"IMAGE", "VIDEO", "AUDIO", "AV"}:
            raise ValueError(f"unsupported bridge mode: {self.mode}")

        frame_count = len(self.frames)
        expected_counts = {"IMAGE": (1, 1), "VIDEO": (2, None), "AUDIO": (0, 0), "AV": (1, None)}
        minimum, maximum = expected_counts[self.mode]
        if frame_count < minimum or (maximum is not None and frame_count > maximum):
            raise ValueError(f"mode {self.mode} has an invalid number of frames")
        needs_audio = self.mode in {"AUDIO", "AV"}
        if (self.audio is not None) is not needs_audio:
            raise ValueError(f"mode {self.mode} has an invalid audio presence mask")
        if self.audio is not None and (self.audio.start_ms, self.audio.end_ms) != (
            self.start_ms,
            self.end_ms,
        ):
            raise ValueError("audio feature interval must match the batch source interval")

        pts = tuple(frame.pts_ms for frame in self.frames)
        if any(not self.start_ms <= pts_ms < self.end_ms for pts_ms in pts):
            raise ValueError("frame source PTS must fall within the batch interval")
        if any(left >= right for left, right in zip(pts, pts[1:], strict=False)):
            raise ValueError("frame source PTS must be strictly increasing")

        sequences = [frame.tokens for frame in self.frames]
        if self.audio is not None:
            sequences.append(self.audio.tokens)
        revisions = {sequence.model_revision for sequence in sequences}
        dimensions = {sequence.embeddings.shape[1] for sequence in sequences}
        if len(revisions) > 1 or len(dimensions) > 1:
            raise ValueError(
                "all modality features must share an encoder revision and feature width"
            )

    @property
    def modality_present(self) -> dict[str, bool]:
        return {"vision": bool(self.frames), "audio": self.audio is not None}

    @classmethod
    def from_records(
        cls,
        *,
        mode: BridgeMode,
        source_id: str,
        epoch: int,
        interval_ms: tuple[int, int],
        frame_records: tuple[SequenceFeatureRecord, ...] = (),
        audio_record: SequenceFeatureRecord | None = None,
    ) -> AVFeatureBatch:
        start_ms, end_ms = interval_ms
        frames = tuple(FrameFeatures.from_record(record) for record in frame_records)
        audio = AudioFeatures.from_record(audio_record) if audio_record is not None else None
        return cls(
            mode=mode,
            source_id=source_id,
            epoch=epoch,
            start_ms=start_ms,
            end_ms=end_ms,
            frames=frames,
            audio=audio,
        )

    def metadata(self) -> dict[str, object]:
        """Return non-tensor provenance suitable for reports and cache manifests."""
        return {
            "mode": self.mode,
            "source_id": self.source_id,
            "epoch": self.epoch,
            "interval_ms": [self.start_ms, self.end_ms],
            "modality_present": self.modality_present,
            "frame_pts_ms": [frame.pts_ms for frame in self.frames],
            "frame_token_shapes": [list(frame.tokens.embeddings.shape) for frame in self.frames],
            "audio_interval_ms": (
                [self.audio.start_ms, self.audio.end_ms] if self.audio is not None else None
            ),
            "audio_token_shape": (
                list(self.audio.tokens.embeddings.shape) if self.audio is not None else None
            ),
            "model_revision": next(
                (sequence.model_revision for sequence in self._sequences()), None
            ),
            "preprocess_versions": [sequence.preprocess_version for sequence in self._sequences()],
        }

    def _sequences(self) -> tuple[TokenSequence, ...]:
        sequences = tuple(frame.tokens for frame in self.frames)
        return sequences + ((self.audio.tokens,) if self.audio is not None else ())
