"""Bounded activity-driven embedding sampling with periodic heartbeats."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from threading import Lock
from typing import Literal

import numpy as np

from shsd.detectors.types import SignalObservation
from shsd.embeddings.cache import normalize_embedding

SamplingProfile = Literal["standard", "adaptive"]


@dataclass(frozen=True, slots=True)
class SamplingDecision:
    selected: bool
    reason: str
    activity_score: float


@dataclass(frozen=True, slots=True)
class EmbeddingNovelty:
    """Cosine distance to the previous compatible, semantically accepted vector."""

    comparable: bool
    cosine_similarity: float | None
    novelty_score: float | None
    reference_window_id: str | None


class AdaptiveSamplingController:
    """Use cheap signal changes to reduce embeddings while bounding blind gaps.

    Audio changes are measured against a comparable previous window; video uses
    low-resolution frame difference. Uncomparable audio windows are admitted
    conservatively. Quiet audio and static video are still sampled at
    ``heartbeat_windows`` so long, low-energy content is not silently ignored.
    A separate minimum stride prevents noisy video from triggering an embedding
    for every decoded frame.
    """

    def __init__(
        self,
        *,
        profile: SamplingProfile,
        window_ms: int,
        heartbeat_windows: int = 3,
        video_difference_threshold: float = 0.04,
        audio_loudness_delta_db_threshold: float = 3.0,
        audio_vad_fraction_delta_threshold: float = 0.10,
        audio_centroid_delta_hz_threshold: float = 200.0,
        audio_onset_count_delta_threshold: float = 5.0,
    ) -> None:
        if profile not in {"standard", "adaptive"}:
            raise ValueError("sampling profile must be standard or adaptive")
        if window_ms < 250:
            raise ValueError("window_ms must be at least 250")
        if heartbeat_windows < 2:
            raise ValueError("heartbeat_windows must be at least 2")
        if not 0 < video_difference_threshold <= 1:
            raise ValueError("video_difference_threshold must be in (0, 1]")
        if audio_loudness_delta_db_threshold <= 0:
            raise ValueError("audio_loudness_delta_db_threshold must be positive")
        if not 0 < audio_vad_fraction_delta_threshold <= 1:
            raise ValueError("audio_vad_fraction_delta_threshold must be in (0, 1]")
        if audio_centroid_delta_hz_threshold <= 0:
            raise ValueError("audio_centroid_delta_hz_threshold must be positive")
        if audio_onset_count_delta_threshold <= 0:
            raise ValueError("audio_onset_count_delta_threshold must be positive")
        self.profile = profile
        self.window_ms = window_ms
        self.heartbeat_ms = window_ms * heartbeat_windows
        self.video_difference_threshold = video_difference_threshold
        self.audio_loudness_delta_db_threshold = audio_loudness_delta_db_threshold
        self.audio_vad_fraction_delta_threshold = audio_vad_fraction_delta_threshold
        self.audio_centroid_delta_hz_threshold = audio_centroid_delta_hz_threshold
        self.audio_onset_count_delta_threshold = audio_onset_count_delta_threshold
        self._last_audio_sample_ms: int | None = None
        self._last_video_sample_ms: int | None = None
        self._previous_video: np.ndarray | None = None
        self._accepted_embeddings: dict[str, tuple[np.ndarray, str, str, str]] = {}
        self._embedding_novelty: dict[str, dict[str, int | float | str | bool | None]] = {
            modality: {
                "comparisons": 0,
                "accepted_references": 0,
                "last_comparable": False,
                "last_cosine_similarity": None,
                "last_novelty_score": None,
                "reference_window_id": None,
                "current_window_id": None,
            }
            for modality in ("audio", "video")
        }
        self._counts: dict[str, dict[str, int]] = {
            modality: {
                "opportunities": 0,
                "selected": 0,
                "activity": 0,
                "heartbeat": 0,
                "standard": 0,
                "uncomparable": 0,
                "stride_limited": 0,
                "runtime_backpressure": 0,
                "skipped": 0,
            }
            for modality in ("audio", "video")
        }
        self._lock = Lock()

    def select_audio(
        self,
        start_ms: int,
        observations: Sequence[SignalObservation],
        *,
        signal_changes: Sequence[SignalObservation] | None = None,
    ) -> SamplingDecision:
        """Admit audio on signal changes, falling back to a bounded heartbeat.

        ``signal_changes`` should contain measurements for a comparable previous
        window. If changes are unavailable (first, overlapping, or out-of-order
        windows), the controller samples instead of assuming the signal is stable.
        """
        if start_ms < 0:
            raise ValueError("start_ms must be non-negative")
        signal_score = self._audio_signal_score(observations)
        if self.profile == "standard":
            return self._record("audio", True, "standard", signal_score)

        score, comparable = self._audio_change_score(signal_changes)
        if not comparable:
            score = signal_score
        changed = comparable and score >= 1.0

        last = self._last_audio_sample_ms
        heartbeat_due = last is None or start_ms - last >= self.heartbeat_ms
        stride_due = last is None or start_ms - last >= self.window_ms
        uncomparable = not comparable
        selected = stride_due and (changed or heartbeat_due or uncomparable)
        reason = (
            "stride_limited"
            if not stride_due
            else "uncomparable"
            if uncomparable
            else
            "activity"
            if changed
            else "heartbeat"
            if heartbeat_due
            else "stable_audio"
        )
        if selected:
            self._last_audio_sample_ms = start_ms
        return self._record("audio", selected, reason, score)

    def select_video(
        self,
        frame_ms: int,
        small_rgb_frame: np.ndarray,
        *,
        standard_due: bool,
        minimum_stride_ms: int | None = None,
    ) -> SamplingDecision:
        """Decide whether a low-resolution frame merits a full-frame embedding."""
        if frame_ms < 0:
            raise ValueError("frame_ms must be non-negative")
        if minimum_stride_ms is not None and minimum_stride_ms < self.window_ms:
            raise ValueError("minimum_stride_ms cannot be shorter than window_ms")
        frame = np.asarray(small_rgb_frame, dtype=np.uint8)
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("small_rgb_frame must have shape (height, width, 3)")
        previous = self._previous_video
        difference = (
            1.0
            if previous is None
            else float(np.abs(frame.astype(np.int16) - previous.astype(np.int16)).mean() / 255.0)
        )
        self._previous_video = frame.copy()
        if self.profile == "standard":
            if standard_due:
                self._last_video_sample_ms = frame_ms
            return self._record("video", standard_due, "standard", difference)

        active = difference >= self.video_difference_threshold
        last = self._last_video_sample_ms
        heartbeat_due = last is None or frame_ms - last >= self.heartbeat_ms
        minimum_stride = max(self.window_ms, minimum_stride_ms or self.window_ms)
        stride_due = (
            frame_ms >= minimum_stride
            if last is None and minimum_stride > self.window_ms
            else last is None or frame_ms - last >= minimum_stride
        )
        selected = stride_due and (active or heartbeat_due)
        reason = (
            "runtime_backpressure"
            if not stride_due and minimum_stride > self.window_ms
            else
            "activity"
            if selected and active
            else "heartbeat"
            if selected
            else "stable_video"
        )
        if selected:
            self._last_video_sample_ms = frame_ms
        activity_score = min(1.0, difference / self.video_difference_threshold)
        return self._record("video", selected, reason, activity_score)

    def record_standard_video(self, selected: bool, *, runtime_backpressure: bool = False) -> None:
        """Count a standard-stride decision without extra frame conversion."""
        if self.profile != "standard":
            return
        self._record(
            "video",
            selected,
            "runtime_backpressure" if runtime_backpressure else "standard",
            0.0,
        )

    def rollback_video_sample(self, frame_ms: int) -> None:
        """Release an adaptive stride when the selected frame is later dropped."""
        with self._lock:
            if self._last_video_sample_ms == frame_ms:
                self._last_video_sample_ms = None

    def compare_accepted_embedding(
        self,
        modality: str,
        embedding: np.ndarray,
        *,
        model_revision: str,
        preprocess_version: str,
        window_id: str,
    ) -> EmbeddingNovelty:
        """Compare a vector to the last accepted state without updating that state."""
        if modality not in self._embedding_novelty:
            raise ValueError("embedding novelty supports audio and video modalities")
        if not model_revision or not preprocess_version or not window_id:
            raise ValueError("embedding comparison requires profile and window identifiers")
        normalized = normalize_embedding(embedding)
        with self._lock:
            previous = self._accepted_embeddings.get(modality)
            comparable = previous is not None and previous[1:3] == (
                model_revision,
                preprocess_version,
            )
            similarity: float | None = None
            novelty_score: float | None = None
            reference_window_id = previous[3] if previous is not None else None
            if comparable and previous is not None:
                similarity = float(np.clip(np.dot(previous[0], normalized), -1.0, 1.0))
                novelty_score = round(min(1.0, max(0.0, 1.0 - similarity)), 6)
            stats = self._embedding_novelty[modality]
            stats["comparisons"] = int(stats["comparisons"] or 0) + int(comparable)
            stats["last_comparable"] = comparable
            stats["last_cosine_similarity"] = (
                round(similarity, 6) if similarity is not None else None
            )
            stats["last_novelty_score"] = novelty_score
            stats["reference_window_id"] = reference_window_id
            stats["current_window_id"] = window_id
        return EmbeddingNovelty(
            comparable=comparable,
            cosine_similarity=similarity,
            novelty_score=novelty_score,
            reference_window_id=reference_window_id,
        )

    def accept_embedding(
        self,
        modality: str,
        embedding: np.ndarray,
        *,
        model_revision: str,
        preprocess_version: str,
        window_id: str,
    ) -> None:
        """Advance the comparison baseline after a window has an accepted L1 claim."""
        if modality not in self._embedding_novelty:
            raise ValueError("embedding novelty supports audio and video modalities")
        if not model_revision or not preprocess_version or not window_id:
            raise ValueError("accepted embedding requires profile and window identifiers")
        normalized = normalize_embedding(embedding)
        with self._lock:
            self._accepted_embeddings[modality] = (
                normalized,
                model_revision,
                preprocess_version,
                window_id,
            )
            stats = self._embedding_novelty[modality]
            stats["accepted_references"] = int(stats["accepted_references"] or 0) + 1

    def snapshot(self) -> dict[str, object]:
        """Return sampling decisions and configured maximum quiet interval."""
        with self._lock:
            modalities = {key: dict(value) for key, value in self._counts.items()}
            embedding_novelty = {
                key: dict(value) for key, value in self._embedding_novelty.items()
            }
        return {
            "profile": self.profile,
            "heartbeat_ms": self.heartbeat_ms,
            "video_difference_threshold": self.video_difference_threshold,
            "audio_loudness_delta_db_threshold": self.audio_loudness_delta_db_threshold,
            "audio_vad_fraction_delta_threshold": self.audio_vad_fraction_delta_threshold,
            "audio_centroid_delta_hz_threshold": self.audio_centroid_delta_hz_threshold,
            "audio_onset_count_delta_threshold": self.audio_onset_count_delta_threshold,
            "modalities": modalities,
            "embedding_novelty": embedding_novelty,
        }

    def _audio_change_score(
        self,
        signal_changes: Sequence[SignalObservation] | None,
    ) -> tuple[float, bool]:
        if not signal_changes:
            return 0.0, False
        thresholds = {
            "loudness_delta_db": self.audio_loudness_delta_db_threshold,
            "activity_fraction_delta": self.audio_vad_fraction_delta_threshold,
            "spectral_centroid_delta_hz": self.audio_centroid_delta_hz_threshold,
            "onset_count_delta": self.audio_onset_count_delta_threshold,
        }
        ratios = [
            abs(float(item.value)) / thresholds[item.subtype]
            for item in signal_changes
            if item.subtype in thresholds
            and isinstance(item.value, (int, float))
            and not isinstance(item.value, bool)
        ]
        if not ratios:
            return 0.0, False
        return min(1.0, max(ratios)), True

    @staticmethod
    def _audio_signal_score(observations: Sequence[SignalObservation]) -> float:
        vad = [
            bool(item.value)
            for item in observations
            if item.subtype == "energy_vad" and isinstance(item.value, bool)
        ]
        active_fraction = sum(vad) / len(vad) if vad else 0.0
        novelty = max(
            (
                float(item.value)
                for item in observations
                if item.subtype in {"spectral_novelty", "onset"}
                and isinstance(item.value, (int, float))
                and not isinstance(item.value, bool)
            ),
            default=0.0,
        )
        return round(max(active_fraction, min(1.0, novelty)), 6)

    def _record(
        self,
        modality: str,
        selected: bool,
        reason: str,
        activity_score: float,
    ) -> SamplingDecision:
        with self._lock:
            counts = self._counts[modality]
            counts["opportunities"] += 1
            counts["selected" if selected else "skipped"] += 1
            if reason == "runtime_backpressure":
                counts["runtime_backpressure"] += 1
            if reason == "stride_limited":
                counts["stride_limited"] += 1
            if selected and reason in counts:
                counts[reason] += 1
        return SamplingDecision(selected, reason, round(activity_score, 6))
