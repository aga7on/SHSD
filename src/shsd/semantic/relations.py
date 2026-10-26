"""Bounded PTS-based correlation of cheap audio onsets and video scene cuts."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

from shsd.detectors.types import SignalObservation


@dataclass(frozen=True, slots=True)
class CrossModalMatch:
    audio_onset: SignalObservation
    scene_cut: SignalObservation
    delta_ms: int

    @property
    def start_ms(self) -> int:
        return min(self.audio_onset.start_ms, self.scene_cut.start_ms)

    @property
    def end_ms(self) -> int:
        return max(self.audio_onset.end_ms, self.scene_cut.end_ms)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "temporally_coincident",
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "scene_cut_time_ms": self.scene_cut.end_ms,
            "audio_onset_time_ms": (self.audio_onset.start_ms + self.audio_onset.end_ms) // 2,
            "delta_ms": self.delta_ms,
            "evidence_refs": [
                (
                    f"audio:onset:{self.audio_onset.start_ms}-{self.audio_onset.end_ms}:"
                    f"{self.audio_onset.method_version}"
                ),
                (
                    f"video:scene_cut:{self.scene_cut.start_ms}-{self.scene_cut.end_ms}:"
                    f"{self.scene_cut.method_version}"
                ),
            ],
            "causality_claimed": False,
        }


@dataclass(frozen=True, slots=True)
class CrossModalAssessment:
    status: Literal["assessed", "unavailable", "truncated"]
    audio_onset_count: int
    scene_cut_count: int
    matches: tuple[CrossModalMatch, ...]
    unmatched_scene_cut_count: int
    unmatched_audio_onset_count: int
    unavailable_modalities: tuple[str, ...]
    dropped_audio_count: int
    dropped_video_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "audio_onset_count": self.audio_onset_count,
            "scene_cut_count": self.scene_cut_count,
            "matched_count": len(self.matches),
            "unmatched_scene_cut_count": self.unmatched_scene_cut_count,
            "unmatched_audio_onset_count": self.unmatched_audio_onset_count,
            "unavailable_modalities": list(self.unavailable_modalities),
            "dropped_audio_count": self.dropped_audio_count,
            "dropped_video_count": self.dropped_video_count,
            "causality_claimed": False,
        }


class CrossModalRelationValidator:
    """Match distinct onset/cut observations within a PTS tolerance and fixed memory cap."""

    def __init__(
        self,
        *,
        tolerance_ms: int = 250,
        bucket_ms: int = 125,
        max_observations: int = 25_000,
    ) -> None:
        if tolerance_ms < 0 or bucket_ms < 1 or max_observations < 1:
            raise ValueError("tolerance must be non-negative and bucket/capacity positive")
        self.tolerance_ms = tolerance_ms
        self.bucket_ms = bucket_ms
        self.max_observations = max_observations
        self._audio: dict[int, SignalObservation] = {}
        self._audio_order: deque[int] = deque()
        self._video: deque[SignalObservation] = deque()
        self._dropped_audio = 0
        self._dropped_video = 0

    def add_audio(self, observation: SignalObservation) -> None:
        """Retain only the strongest detected onset in each small PTS bucket."""
        if observation.subtype != "onset" or isinstance(observation.value, bool):
            return
        bucket = observation.start_ms // self.bucket_ms
        existing = self._audio.get(bucket)
        if existing is not None:
            if float(observation.value) > float(existing.value):
                self._audio[bucket] = observation
            return
        self._audio[bucket] = observation
        self._audio_order.append(bucket)
        if len(self._audio_order) > self.max_observations:
            expired = self._audio_order.popleft()
            del self._audio[expired]
            self._dropped_audio += 1

    def add_video(self, observation: SignalObservation) -> None:
        """Retain timestamped scene-cut observations in bounded order."""
        if observation.subtype != "scene_cut" or observation.value is not True:
            return
        if len(self._video) == self.max_observations:
            self._video.popleft()
            self._dropped_video += 1
        self._video.append(observation)

    def assess(self, *, available_modalities: set[str]) -> CrossModalAssessment:
        """Pair each cut with at most one nearest audio onset, without causal language."""
        unavailable = tuple(
            modality for modality in ("audio", "video") if modality not in available_modalities
        )
        audio = sorted(self._audio.values(), key=lambda item: (item.start_ms, item.end_ms))
        video = sorted(self._video, key=lambda item: (item.end_ms, item.start_ms))
        if unavailable:
            return CrossModalAssessment(
                status="unavailable",
                audio_onset_count=len(audio),
                scene_cut_count=len(video),
                matches=(),
                unmatched_scene_cut_count=0,
                unmatched_audio_onset_count=0,
                unavailable_modalities=unavailable,
                dropped_audio_count=self._dropped_audio,
                dropped_video_count=self._dropped_video,
            )

        used_audio: set[int] = set()
        matches: list[CrossModalMatch] = []
        unmatched_cuts = 0
        for scene_cut in video:
            cut_time = scene_cut.end_ms
            best_index: int | None = None
            best_delta = self.tolerance_ms + 1
            for index, onset in enumerate(audio):
                if index in used_audio:
                    continue
                onset_time = (onset.start_ms + onset.end_ms) // 2
                delta = abs(onset_time - cut_time)
                if delta < best_delta:
                    best_index = index
                    best_delta = delta
            if best_index is None or best_delta > self.tolerance_ms:
                unmatched_cuts += 1
                continue
            used_audio.add(best_index)
            matches.append(CrossModalMatch(audio[best_index], scene_cut, best_delta))

        unmatched_audio = len(audio) - len(used_audio)
        truncated = self._dropped_audio > 0 or self._dropped_video > 0
        return CrossModalAssessment(
            status="truncated" if truncated else "assessed",
            audio_onset_count=len(audio),
            scene_cut_count=len(video),
            matches=tuple(matches),
            unmatched_scene_cut_count=unmatched_cuts,
            unmatched_audio_onset_count=unmatched_audio,
            unavailable_modalities=(),
            dropped_audio_count=self._dropped_audio,
            dropped_video_count=self._dropped_video,
        )
