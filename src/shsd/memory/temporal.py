"""Persistence and hysteresis for contiguous semantic window matches."""

from __future__ import annotations

import math
import uuid
from collections import deque
from dataclasses import dataclass, replace

from shsd.detectors.types import SignalObservation
from shsd.memory.models import TimelineClaim, TimelineEvent

MAX_SEEN_WINDOWS = 4096
MAX_EVENT_WINDOWS = 64
MAX_EVENT_EVIDENCE_REFS = 128


@dataclass(frozen=True, slots=True)
class WindowMatch:
    stream_id: str
    epoch: int
    start_ms: int
    end_ms: int
    axis_id: str
    candidate_id: str
    text_ru: str | None
    decision: str
    raw_cosine: float
    margin: float
    modality: str
    evidence_refs: tuple[str, ...]
    window_id: str
    model_revision: str
    candidate_independent: bool = False
    candidate_hypotheses: tuple[tuple[str, float, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.stream_id or not self.axis_id or not self.window_id:
            raise ValueError("stream_id, axis_id, and window_id must be non-empty")
        if self.epoch < 0 or self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("window interval and epoch are invalid")
        if self.decision not in {"accepted", "uncertain", "rejected"}:
            raise ValueError("window decision must be accepted, uncertain, or rejected")
        if not math.isfinite(self.raw_cosine) or not -1.0 <= self.raw_cosine <= 1.0:
            raise ValueError("raw_cosine must be finite and between -1 and 1")
        if not math.isfinite(self.margin) or not 0.0 <= self.margin <= 2.0:
            raise ValueError("margin must be finite and between 0 and 2")
        if not self.evidence_refs:
            raise ValueError("window matches require evidence_refs")
        if self.modality not in {"audio", "image", "video", "speech", "joint"}:
            raise ValueError("unsupported window modality")
        if not self.model_revision:
            raise ValueError("model_revision must be non-empty")


class TemporalEventReducer:
    """Require repeated matches, then extend one stable event across overlapping windows."""

    def __init__(self, *, min_repeats: int = 2, max_gap_ms: int = 1500) -> None:
        if min_repeats < 1 or max_gap_ms < 0:
            raise ValueError("min_repeats must be positive and max_gap_ms non-negative")
        self.min_repeats = min_repeats
        self.max_gap_ms = max_gap_ms
        self._pending: dict[tuple[str, int, str, str], list[WindowMatch]] = {}
        self._active: dict[tuple[str, int, str, str], TimelineEvent] = {}
        self._last: dict[tuple[str, int, str, str], WindowMatch] = {}
        self._seen_windows: set[tuple[str, int, str, str, str]] = set()
        self._seen_order: deque[tuple[str, int, str, str, str]] = deque()
        self._current_epoch: dict[str, int] = {}

    def ingest(self, match: WindowMatch) -> TimelineEvent | None:
        """Return a new event revision only after a stable match or active extension."""
        current_epoch = self._current_epoch.get(match.stream_id)
        if current_epoch is not None and match.epoch < current_epoch:
            raise ValueError(
                f"stale match from epoch {match.epoch}; current epoch is {current_epoch}"
            )
        if current_epoch is not None and match.epoch > current_epoch:
            self._discard_older_epochs(match.stream_id, match.epoch)
        self._current_epoch[match.stream_id] = match.epoch
        candidate_key = match.candidate_id if match.candidate_independent else ""
        key = (match.stream_id, match.epoch, match.axis_id, candidate_key)
        seen_key = (*key, match.window_id)
        if seen_key in self._seen_windows:
            return None
        previous = self._last.get(key)
        if previous is not None and match.start_ms < previous.start_ms:
            raise ValueError("window matches must arrive in non-decreasing source-time order")
        if len(self._seen_order) == MAX_SEEN_WINDOWS:
            expired = self._seen_order.popleft()
            self._seen_windows.discard(expired)
        self._seen_order.append(seen_key)
        self._seen_windows.add(seen_key)
        self._last[key] = match

        if match.decision == "rejected":
            self._pending.pop(key, None)
            return None

        pending = self._pending.get(key, [])
        contiguous = False
        if pending:
            prior = pending[-1]
            gap_ms = max(0, match.start_ms - prior.end_ms)
            same_hypothesis = (
                match.candidate_id == prior.candidate_id
                and match.model_revision == prior.model_revision
                and match.decision == prior.decision
            )
            contiguous = same_hypothesis and gap_ms <= self.max_gap_ms
            if not contiguous:
                pending = []
        pending.append(match)
        self._pending[key] = pending

        active = self._active.get(key)
        active_claim = active.claims[0] if active is not None else None
        active_is_contiguous = (
            active is not None
            and active_claim is not None
            and active_claim.label == match.candidate_id
            and active_claim.decision == match.decision
            and max(0, match.start_ms - active.end_ms) <= self.max_gap_ms
        )
        if contiguous and active_is_contiguous and active is not None:
            event = self._revise(active, pending)
            self._active[key] = event
            self._pending[key] = [match]
            return event
        if len(pending) < self.min_repeats:
            return None

        previous_candidate = active.claims[0].label if active is not None else None
        event = self._new_event(match, pending, previous_candidate=previous_candidate)
        self._active[key] = event
        self._pending[key] = [match]
        return event

    def ingest_signal(
        self,
        stream_id: str,
        epoch: int,
        observation: SignalObservation,
        *,
        window_id: str,
    ) -> TimelineEvent | None:
        """Turn a positive cheap scene-cut observation into a measured L0 event."""
        if not stream_id or not window_id or epoch < 0:
            raise ValueError("stream_id/window_id must be non-empty and epoch non-negative")
        if observation.subtype != "scene_cut" or observation.value is not True:
            return None
        current_epoch = self._current_epoch.get(stream_id)
        if current_epoch is not None and epoch < current_epoch:
            raise ValueError(f"stale signal from epoch {epoch}; current epoch is {current_epoch}")
        if current_epoch is not None and epoch > current_epoch:
            self._discard_older_epochs(stream_id, epoch)
        self._current_epoch[stream_id] = epoch
        key = (stream_id, epoch, "signal.scene_cut", "")
        seen_key = (*key, window_id)
        if seen_key in self._seen_windows:
            return None
        if len(self._seen_order) == MAX_SEEN_WINDOWS:
            expired = self._seen_order.popleft()
            self._seen_windows.discard(expired)
        self._seen_order.append(seen_key)
        self._seen_windows.add(seen_key)
        claim = TimelineClaim(
            claim_id=f"claim-scene-cut-{window_id}",
            label="scene_cut",
            text_ru="Обнаружено заметное изменение изображения.",
            decision="accepted",
            raw_cosine=None,
            margin=None,
            evidence_refs=(
                f"video:{observation.start_ms}-{observation.end_ms}",
                f"method:{observation.method_version}",
            ),
            window_ids=(window_id,),
            model_revision=observation.method_version,
            sample_count=1,
        )
        return TimelineEvent(
            stream_id=stream_id,
            epoch=epoch,
            event_id=uuid.uuid4().hex,
            revision=1,
            start_ms=observation.start_ms,
            end_ms=observation.end_ms,
            kind="scene_changed",
            level="L0",
            state="committed",
            modality_mask={"audio": False, "video": True, "speech": False},
            claims=(claim,),
        )

    def _discard_older_epochs(self, stream_id: str, new_epoch: int) -> None:
        for state in (self._pending, self._active, self._last):
            for key in tuple(state):
                if key[0] == stream_id and key[1] < new_epoch:
                    del state[key]
        retained = [
            key for key in self._seen_order if key[0] != stream_id or key[1] >= new_epoch
        ]
        self._seen_order = deque(retained)
        self._seen_windows = set(retained)

    @staticmethod
    def _kind(
        axis_id: str,
        candidate_id: str,
        decision: str,
        previous_candidate: str | None,
    ) -> str:
        if candidate_id == "unknown" or decision != "accepted":
            return "unknown"
        if axis_id == "music_presence":
            if candidate_id == "music_absent":
                return "music_stopped"
            if candidate_id in {"music_present", "music_and_speech"}:
                if previous_candidate in {"music_present", "music_absent", None}:
                    return "music_started"
                return "music_changed"
            return "audio_scene_changed"
        if axis_id == "speech_presence" and candidate_id == "speech_present":
            return "speech_detected"
        if axis_id == "impact_sound" and candidate_id == "impact_present":
            return "sound_effect"
        if axis_id == "instrument_family":
            return (
                "instrument_change"
                if previous_candidate is not None and previous_candidate != candidate_id
                else "instrument_detected"
            )
        if axis_id.startswith("scene_") or axis_id.startswith("person_"):
            return "scene_changed" if previous_candidate is not None else "visual_scene"
        if axis_id.startswith("visual_"):
            return "visual_change" if previous_candidate is not None else "visual_scene"
        if previous_candidate is not None:
            return "semantic_change"
        return "unknown"

    @staticmethod
    def _claim(matches: list[WindowMatch]) -> TimelineClaim:
        latest = matches[-1]
        refs = tuple(dict.fromkeys(ref for item in matches for ref in item.evidence_refs))
        windows = tuple(dict.fromkeys(item.window_id for item in matches))
        return TimelineClaim(
            claim_id=f"claim-{latest.axis_id}-{latest.candidate_id}",
            label=latest.candidate_id,
            text_ru=latest.text_ru,
            decision=(
                "accepted"
                if all(item.decision == "accepted" for item in matches)
                else "uncertain"
            ),
            raw_cosine=sum(item.raw_cosine for item in matches) / len(matches),
            margin=min(item.margin for item in matches),
            evidence_refs=refs,
            window_ids=windows,
            model_revision=latest.model_revision,
            sample_count=len(matches),
            candidate_hypotheses=TemporalEventReducer._aggregate_candidate_hypotheses(matches),
        )

    @staticmethod
    def _aggregate_candidate_hypotheses(
        matches: list[WindowMatch],
    ) -> tuple[tuple[str, float, str], ...]:
        samples: dict[str, list[tuple[float, str]]] = {}
        for match in matches:
            for candidate_id, raw_cosine, decision in match.candidate_hypotheses:
                samples.setdefault(candidate_id, []).append((raw_cosine, decision))
        aggregate = [
            (
                candidate_id,
                sum(score for score, _decision in entries) / len(entries),
                (
                    "accepted"
                    if all(decision == "accepted" for _score, decision in entries)
                    else "uncertain"
                ),
            )
            for candidate_id, entries in samples.items()
        ]
        return tuple(sorted(aggregate, key=lambda item: item[1], reverse=True))

    def _new_event(
        self,
        match: WindowMatch,
        matches: list[WindowMatch],
        *,
        previous_candidate: str | None,
    ) -> TimelineEvent:
        modality_mask = {"audio": False, "video": False, "speech": False}
        for item in matches:
            if item.modality in {"audio", "joint"}:
                modality_mask["audio"] = True
            if item.modality in {"image", "video", "joint"}:
                modality_mask["video"] = True
            if item.modality == "speech":
                modality_mask["speech"] = True
        return TimelineEvent(
            stream_id=match.stream_id,
            epoch=match.epoch,
            event_id=uuid.uuid4().hex,
            revision=1,
            start_ms=matches[0].start_ms,
            end_ms=max(item.end_ms for item in matches),
            kind=self._kind(
                match.axis_id,
                match.candidate_id,
                match.decision,
                previous_candidate,
            ),
            level="L1",
            state="draft",
            modality_mask=modality_mask,
            claims=(self._claim(matches),),
        )

    def _revise(self, active: TimelineEvent, matches: list[WindowMatch]) -> TimelineEvent:
        prior_claim = active.claims[0]
        additions = [item for item in matches if item.window_id not in prior_claim.window_ids]
        if not additions:
            return active
        addition_count = len(additions)
        combined_count = prior_claim.sample_count + addition_count
        previous_sum = (prior_claim.raw_cosine or 0.0) * prior_claim.sample_count
        added_sum = sum(item.raw_cosine for item in additions)
        claim = replace(
            prior_claim,
            decision=(
                "accepted"
                if prior_claim.decision == "accepted"
                and all(item.decision == "accepted" for item in additions)
                else "uncertain"
            ),
            raw_cosine=(previous_sum + added_sum) / combined_count,
            margin=min([prior_claim.margin or 0.0, *(item.margin for item in additions)]),
            evidence_refs=tuple(
                dict.fromkeys(
                    [
                        *prior_claim.evidence_refs,
                        *(ref for item in additions for ref in item.evidence_refs),
                    ]
                )
            )[-MAX_EVENT_EVIDENCE_REFS:],
            window_ids=tuple(
                dict.fromkeys([*prior_claim.window_ids, *(item.window_id for item in additions)])
            )[-MAX_EVENT_WINDOWS:],
            sample_count=combined_count,
            candidate_hypotheses=TemporalEventReducer._aggregate_candidate_hypotheses(
                [
                    WindowMatch(
                        stream_id=active.stream_id,
                        epoch=active.epoch,
                        start_ms=active.start_ms,
                        end_ms=active.end_ms,
                        axis_id="aggregate",
                        candidate_id=prior_claim.label,
                        text_ru=prior_claim.text_ru,
                        decision=prior_claim.decision,
                        raw_cosine=prior_claim.raw_cosine or 0.0,
                        margin=prior_claim.margin or 0.0,
                        modality="audio",
                        evidence_refs=prior_claim.evidence_refs,
                        window_id=f"aggregate:{active.event_id}:{prior_claim.sample_count}",
                        model_revision=prior_claim.model_revision,
                        candidate_hypotheses=tuple(
                            (candidate_id, score, decision)
                            for candidate_id, score, decision in prior_claim.candidate_hypotheses
                            for _ in range(prior_claim.sample_count)
                        ),
                    ),
                    *additions,
                ]
            ),
        )
        mask = dict(active.modality_mask)
        for item in additions:
            if item.modality in {"audio", "joint"}:
                mask["audio"] = True
            if item.modality in {"image", "video", "joint"}:
                mask["video"] = True
            if item.modality == "speech":
                mask["speech"] = True
        return TimelineEvent(
            stream_id=active.stream_id,
            epoch=active.epoch,
            event_id=active.event_id,
            revision=active.revision + 1,
            start_ms=active.start_ms,
            end_ms=max(active.end_ms, *(item.end_ms for item in additions)),
            kind=active.kind,
            level=active.level,
            state=active.state,
            modality_mask=mask,
            claims=(claim,),
            caption_ru=active.caption_ru,
            supersedes_revision=active.revision,
        )
