"""State snapshots and novelty deltas derived from stable timeline events."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, replace

from shsd.memory.models import TimelineClaim, TimelineEvent

MAX_SEEN_STATE_WINDOWS = 4096
MAX_SEEN_STATE_EVENTS = 4096


@dataclass(frozen=True, slots=True)
class TemporalStateSnapshot:
    """Current semantic state for one stream epoch."""

    stream_id: str
    epoch: int
    active_music: str | None = None
    active_scene: str | None = None
    active_speakers: tuple[str, ...] = ()
    last_meaningful_change_ms: int | None = None

    def to_dict(self) -> dict[str, int | str | list[str] | None]:
        """Return a JSON-compatible snapshot."""
        result = asdict(self)
        result["active_speakers"] = list(self.active_speakers)
        return result


@dataclass(frozen=True, slots=True)
class TemporalStateDelta:
    """State before and after an event, plus its comparison status."""

    event_id: str
    event_revision: int
    previous: TemporalStateSnapshot
    current: TemporalStateSnapshot
    comparison: str
    novelty_score: float | None
    changed_fields: tuple[str, ...]
    published: bool
    pending: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible state transition."""
        return {
            "event_id": self.event_id,
            "event_revision": self.event_revision,
            "previous": self.previous.to_dict(),
            "current": self.current.to_dict(),
            "comparison": self.comparison,
            "novelty_score": self.novelty_score,
            "changed_fields": list(self.changed_fields),
            "published": self.published,
            "pending": self.pending,
        }


@dataclass(slots=True)
class _PendingChange:
    value: str | tuple[str, ...] | None
    evidence_count: int
    start_ms: int


class TemporalStateReducer:
    """Maintain active semantic state with deduplication and transition hysteresis.

    Input events are expected in source-time order within each state family. A
    candidate that first appears inside an overlapping interval is held pending
    until a non-overlapping event confirms it. Uncertain claims never update the
    snapshot. Accepted L1/L2 events carry their own ``sample_count`` persistence;
    direct measured L0 scene changes are applied immediately.
    """

    _FIELD_BY_KIND = {
        "music_started": "active_music",
        "music_stopped": "active_music",
        "music_changed": "active_music",
        "instrument_change": "active_music",
        "scene_changed": "active_scene",
        "visual_scene": "active_scene",
        "visual_change": "active_scene",
        "speaker_utterance": "active_speakers",
        "speech_detected": "active_speakers",
        "speaker_ended": "active_speakers",
        "speech_stopped": "active_speakers",
    }

    def __init__(self, *, min_repeats: int = 2) -> None:
        if min_repeats < 1:
            raise ValueError("min_repeats must be positive")
        self.min_repeats = min_repeats
        self._states: dict[tuple[str, int], TemporalStateSnapshot] = {}
        self._current_epoch: dict[str, int] = {}
        self._event_revisions: dict[tuple[str, int, str], int] = {}
        self._event_order: deque[tuple[str, int, str]] = deque()
        self._last_intervals: dict[tuple[str, int, str], tuple[int, int]] = {}
        self._pending: dict[tuple[str, int, str], _PendingChange] = {}
        self._seen_windows: set[tuple[str, int, str, str]] = set()
        self._seen_order: deque[tuple[str, int, str, str]] = deque()

    def current(self, stream_id: str, epoch: int) -> TemporalStateSnapshot:
        """Return the current snapshot, or an empty snapshot for the epoch."""
        if not stream_id or epoch < 0:
            raise ValueError("stream_id must be non-empty and epoch non-negative")
        return self._states.get(
            (stream_id, epoch), TemporalStateSnapshot(stream_id=stream_id, epoch=epoch)
        )

    def ingest(self, event: TimelineEvent) -> TemporalStateDelta | None:
        """Apply one event revision or return ``None`` for an already-seen revision."""
        current_epoch = self._current_epoch.get(event.stream_id)
        if current_epoch is not None and event.epoch < current_epoch:
            raise ValueError(
                f"stale event from epoch {event.epoch}; current epoch is {current_epoch}"
            )
        if current_epoch is not None and event.epoch > current_epoch:
            self._discard_older_epochs(event.stream_id, event.epoch)
            self._current_epoch[event.stream_id] = event.epoch
        else:
            self._current_epoch.setdefault(event.stream_id, event.epoch)

        revision_key = (event.stream_id, event.epoch, event.event_id)
        latest_revision = self._event_revisions.get(revision_key)
        if latest_revision is not None and event.revision <= latest_revision:
            return None
        if latest_revision is not None and event.revision != latest_revision + 1:
            raise ValueError("event revisions must arrive consecutively")
        if latest_revision is None:
            if len(self._event_order) == MAX_SEEN_STATE_EVENTS:
                expired = self._event_order.popleft()
                self._event_revisions.pop(expired, None)
            self._event_order.append(revision_key)
        self._event_revisions[revision_key] = event.revision

        snapshot_key = (event.stream_id, event.epoch)
        previous = self._states.get(
            snapshot_key, TemporalStateSnapshot(stream_id=event.stream_id, epoch=event.epoch)
        )
        field_name = self._FIELD_BY_KIND.get(event.kind)
        if field_name is None:
            return self._delta(
                event,
                previous,
                previous,
                comparison="ambiguous",
                novelty_score=None,
                changed_fields=(),
                published=False,
                pending=False,
            )

        family_key = (*snapshot_key, field_name)
        boundary = self._boundary(family_key, event)
        accepted_claims = [claim for claim in event.claims if claim.decision == "accepted"]
        if not accepted_claims:
            self._pending.pop(family_key, None)
            self._remember_interval(family_key, event)
            return self._delta(
                event,
                previous,
                previous,
                comparison="ambiguous",
                novelty_score=None,
                changed_fields=(),
                published=False,
                pending=False,
            )

        if boundary == "out_of_order":
            return self._delta(
                event,
                previous,
                previous,
                comparison="ambiguous",
                novelty_score=None,
                changed_fields=(),
                published=False,
                pending=False,
            )

        new_window_ids, fallback_samples = self._new_window_ids(
            family_key, event, accepted_claims
        )
        if not new_window_ids:
            return None
        self._remember_windows(family_key, new_window_ids)
        target = self._target_value(
            event.kind, field_name, accepted_claims, previous, event.event_id
        )
        before_value = self._field_value(previous, field_name)
        samples = len(new_window_ids) if fallback_samples is None else fallback_samples
        pending = self._pending.get(family_key)

        if target == before_value:
            self._pending.pop(family_key, None)
            self._remember_interval(family_key, event)
            novelty = None if boundary in {"initial", "overlap"} else 0.0
            return self._delta(
                event,
                previous,
                previous,
                comparison=boundary,
                novelty_score=novelty,
                changed_fields=(),
                published=False,
                pending=False,
            )

        if boundary == "overlap":
            self._accumulate_pending(family_key, event, target, samples)
            self._remember_interval(family_key, event)
            return self._delta(
                event,
                previous,
                previous,
                comparison="ambiguous",
                novelty_score=None,
                changed_fields=(),
                published=False,
                pending=True,
            )

        evidence_count = samples
        change_start_ms = event.start_ms
        if pending is not None and pending.value == target:
            evidence_count += pending.evidence_count
            evidence_count = max(evidence_count, pending.evidence_count)
            change_start_ms = pending.start_ms

        direct_measurement = event.level == "L0" and event.kind == "scene_changed"
        if not direct_measurement and evidence_count < self.min_repeats:
            self._pending[family_key] = _PendingChange(
                value=target,
                evidence_count=evidence_count,
                start_ms=change_start_ms,
            )
            self._remember_interval(family_key, event)
            return self._delta(
                event,
                previous,
                previous,
                comparison="pending",
                novelty_score=None,
                changed_fields=(),
                published=False,
                pending=True,
            )

        self._pending.pop(family_key, None)
        updated = self._set_field(
            previous,
            field_name,
            target,
            change_ms=change_start_ms,
        )
        self._states[snapshot_key] = updated
        self._remember_interval(family_key, event)
        novelty = None if before_value is None else 1.0
        return self._delta(
            event,
            previous,
            updated,
            comparison=boundary,
            novelty_score=novelty,
            changed_fields=(field_name,),
            published=True,
            pending=False,
        )

    def _discard_older_epochs(self, stream_id: str, new_epoch: int) -> None:
        for state_key in tuple(self._states):
            if state_key[0] == stream_id and state_key[1] < new_epoch:
                del self._states[state_key]
        for state in (self._last_intervals, self._pending):
            for key in tuple(state):
                if key[0] == stream_id and key[1] < new_epoch:
                    del state[key]
        self._event_order = deque(
            key for key in self._event_order if key[0] != stream_id or key[1] >= new_epoch
        )
        self._event_revisions = {
            key: revision
            for key, revision in self._event_revisions.items()
            if key[0] != stream_id or key[1] >= new_epoch
        }
        self._seen_order = deque(
            key for key in self._seen_order if key[0] != stream_id or key[1] >= new_epoch
        )
        self._seen_windows = set(self._seen_order)

    def _boundary(self, key: tuple[str, int, str], event: TimelineEvent) -> str:
        interval = self._last_intervals.get(key)
        if interval is None:
            return "initial"
        previous_start, previous_end = interval
        if event.start_ms < previous_start:
            return "out_of_order"
        if event.start_ms < previous_end:
            return "overlap"
        if event.start_ms == previous_end:
            return "adjacent"
        return "gap"

    def _remember_interval(self, key: tuple[str, int, str], event: TimelineEvent) -> None:
        previous = self._last_intervals.get(key)
        if previous is None:
            self._last_intervals[key] = (event.start_ms, event.end_ms)
        else:
            self._last_intervals[key] = (
                min(previous[0], event.start_ms),
                max(previous[1], event.end_ms),
            )

    def _accumulate_pending(
        self,
        key: tuple[str, int, str],
        event: TimelineEvent,
        target: str | tuple[str, ...] | None,
        samples: int,
    ) -> None:
        pending = self._pending.get(key)
        if pending is None or pending.value != target:
            self._pending[key] = _PendingChange(
                value=target,
                evidence_count=samples,
                start_ms=event.start_ms,
            )
            return
        self._pending[key] = _PendingChange(
            value=target,
            evidence_count=pending.evidence_count + samples,
            start_ms=pending.start_ms,
        )

    def _new_window_ids(
        self,
        family_key: tuple[str, int, str],
        event: TimelineEvent,
        claims: list[TimelineClaim],
    ) -> tuple[tuple[str, ...], int | None]:
        supplied = tuple(dict.fromkeys(window for claim in claims for window in claim.window_ids))
        if not supplied:
            fallback = f"event:{event.event_id}"
            key = (*family_key, fallback)
            if key in self._seen_windows:
                return (), max(claim.sample_count for claim in claims)
            return (fallback,), max(claim.sample_count for claim in claims)
        new_windows = tuple(
            window
            for window in supplied
            if (*family_key, window) not in self._seen_windows
        )
        return new_windows, None

    def _remember_windows(
        self, family_key: tuple[str, int, str], window_ids: tuple[str, ...]
    ) -> None:
        for window_id in window_ids:
            key = (*family_key, window_id)
            if len(self._seen_order) == MAX_SEEN_STATE_WINDOWS:
                expired = self._seen_order.popleft()
                self._seen_windows.discard(expired)
            self._seen_order.append(key)
            self._seen_windows.add(key)

    @staticmethod
    def _target_value(
        kind: str,
        field_name: str,
        accepted_claims: list[TimelineClaim],
        previous: TemporalStateSnapshot,
        event_id: str,
    ) -> str | tuple[str, ...] | None:
        claim = accepted_claims[0]
        label = claim.label
        if field_name == "active_music":
            return None if kind == "music_stopped" else str(label)
        if field_name == "active_scene":
            return f"scene_cut@{event_id}" if label == "scene_cut" else str(label)

        speakers = set(previous.active_speakers)
        speaker = str(label) if str(label).startswith("speaker_") else "speaker_unknown"
        if kind in {"speaker_utterance", "speech_detected"}:
            speakers.add(speaker)
        elif kind == "speaker_ended":
            speakers.discard(speaker)
        elif kind == "speech_stopped":
            speakers.clear()
        return tuple(sorted(speakers))

    @staticmethod
    def _field_value(
        snapshot: TemporalStateSnapshot, field_name: str
    ) -> str | tuple[str, ...] | None:
        if field_name == "active_speakers":
            return snapshot.active_speakers
        if field_name == "active_music":
            return snapshot.active_music
        if field_name == "active_scene":
            return snapshot.active_scene
        raise ValueError(f"unsupported temporal state field: {field_name}")

    @staticmethod
    def _set_field(
        snapshot: TemporalStateSnapshot,
        field_name: str,
        value: str | tuple[str, ...] | None,
        *,
        change_ms: int,
    ) -> TemporalStateSnapshot:
        if field_name == "active_speakers":
            if not isinstance(value, tuple):
                raise TypeError("active_speakers state must be a tuple")
            return replace(
                snapshot,
                active_speakers=value,
                last_meaningful_change_ms=change_ms,
            )
        if field_name == "active_music":
            if value is not None and not isinstance(value, str):
                raise TypeError("active_music state must be a string or None")
            return replace(snapshot, active_music=value, last_meaningful_change_ms=change_ms)
        if field_name == "active_scene":
            if value is not None and not isinstance(value, str):
                raise TypeError("active_scene state must be a string or None")
            return replace(snapshot, active_scene=value, last_meaningful_change_ms=change_ms)
        raise ValueError(f"unsupported temporal state field: {field_name}")

    @staticmethod
    def _delta(
        event: TimelineEvent,
        previous: TemporalStateSnapshot,
        current: TemporalStateSnapshot,
        *,
        comparison: str,
        novelty_score: float | None,
        changed_fields: tuple[str, ...],
        published: bool,
        pending: bool,
    ) -> TemporalStateDelta:
        return TemporalStateDelta(
            event_id=event.event_id,
            event_revision=event.revision,
            previous=previous,
            current=current,
            comparison=comparison,
            novelty_score=novelty_score,
            changed_fields=changed_fields,
            published=published,
            pending=pending,
        )
