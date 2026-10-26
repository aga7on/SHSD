"""PTS based media clock conversion and epoch management."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

TimeBase = Fraction | tuple[int, int]
EpochReason = Literal["seek", "reconnect", "time_discontinuity"]
Discontinuity = Literal["backward_pts", "forward_gap"]


def _as_fraction(time_base: TimeBase) -> Fraction:
    """Normalize a rational time base without converting through float."""
    if isinstance(time_base, Fraction):
        result = time_base
    else:
        numerator, denominator = time_base
        if denominator == 0:
            raise ValueError("time_base must be a positive rational number")
        result = Fraction(numerator, denominator)
    if result <= 0:
        raise ValueError("time_base must be a positive rational number")
    return result


def _round_fraction(value: Fraction) -> int:
    """Round to nearest integer, with exact half values away from zero."""
    sign = -1 if value < 0 else 1
    numerator = abs(value.numerator)
    whole, remainder = divmod(numerator, value.denominator)
    if remainder * 2 >= value.denominator:
        whole += 1
    return sign * whole


def pts_to_ms(pts: int, time_base: TimeBase, *, offset_ms: int = 0) -> int:
    """Convert a source PTS directly to integer milliseconds.

    Each timestamp is converted from its original rational time base. No
    rounded frame duration is repeatedly accumulated, so VFR streams do not
    build float or rounding drift. ``offset_ms`` supports track start offsets.
    """
    if isinstance(pts, bool) or not isinstance(pts, int):
        raise TypeError("pts must be an integer or a missing PTS")
    return _round_fraction(Fraction(pts) * _as_fraction(time_base) * 1000) + offset_ms


@dataclass(frozen=True, slots=True)
class ClockPoint:
    """Resolved media time for one decoded packet or frame."""

    stream_id: str
    epoch: int
    track_id: str
    pts: int | None
    time_base: Fraction | None
    timestamp_ms: int
    duration_ms: int | None
    timestamp_source: Literal["pts", "fallback"]
    discontinuity: Discontinuity | None = None

    @property
    def start_ms(self) -> int:
        """Half-open interval start in the source timeline."""
        return self.timestamp_ms

    @property
    def end_ms(self) -> int:
        """Half-open interval end; equals start when duration is unknown."""
        return self.timestamp_ms + (self.duration_ms or 0)


@dataclass(frozen=True, slots=True)
class _TrackState:
    timestamp_ms: int
    end_ms: int
    pts: int | None


class MediaClock:
    """Keep source PTS, per-track offsets, and discontinuities for a stream.

    A backward timestamp or a forward gap larger than ``max_forward_gap_ms``
    starts a new epoch. Set the threshold to ``None`` to disable automatic
    forward-gap detection while retaining backward-time detection.
    """

    def __init__(
        self,
        stream_id: str,
        *,
        source_clock: str = "media_pts",
        epoch: int = 0,
        max_forward_gap_ms: int | None = 30_000,
        backward_tolerance_ms: int = 0,
    ) -> None:
        if not stream_id:
            raise ValueError("stream_id must not be empty")
        if epoch < 0:
            raise ValueError("epoch must be non-negative")
        if max_forward_gap_ms is not None and max_forward_gap_ms < 0:
            raise ValueError("max_forward_gap_ms must be non-negative or None")
        if backward_tolerance_ms < 0:
            raise ValueError("backward_tolerance_ms must be non-negative")
        self.stream_id = stream_id
        self.source_clock = source_clock
        self.epoch = epoch
        self.max_forward_gap_ms = max_forward_gap_ms
        self.backward_tolerance_ms = backward_tolerance_ms
        self._track_state: dict[str, _TrackState] = {}
        self._epoch_start_pts: int | None = None
        self.last_reset_reason: EpochReason | Discontinuity | None = None

    @property
    def start_pts(self) -> int | None:
        """First real PTS observed in the current epoch, if one exists."""
        return self._epoch_start_pts

    def begin_epoch(self, reason: EpochReason) -> int:
        """Start a new sequence after seek, reconnect, or known discontinuity."""
        self.epoch += 1
        self._track_state.clear()
        self._epoch_start_pts = None
        self.last_reset_reason = reason
        return self.epoch

    def record_epoch_start_pts(self, pts: int | None) -> None:
        """Record the first available source PTS without assuming packet order."""
        if pts is not None and self._epoch_start_pts is None:
            self._epoch_start_pts = pts

    def observe(
        self,
        track_id: str,
        pts: int | None,
        time_base: TimeBase | None,
        *,
        offset_ms: int = 0,
        duration_ms: int | None = None,
    ) -> ClockPoint:
        """Resolve a PTS or explicitly marked fallback timestamp.

        For missing PTS, use the previous same-track end when known, otherwise
        the configured track offset. The returned point always exposes whether
        its timestamp came from source PTS or a fallback.
        """
        if not track_id:
            raise ValueError("track_id must not be empty")
        if duration_ms is not None and duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")

        previous = self._track_state.get(track_id)
        if pts is None:
            timestamp_ms = previous.end_ms if previous is not None else offset_ms
            point = ClockPoint(
                stream_id=self.stream_id,
                epoch=self.epoch,
                track_id=track_id,
                pts=None,
                time_base=None,
                timestamp_ms=timestamp_ms,
                duration_ms=duration_ms,
                timestamp_source="fallback",
            )
            self._track_state[track_id] = _TrackState(
                timestamp_ms=timestamp_ms,
                end_ms=point.end_ms,
                pts=None,
            )
            return point

        if time_base is None:
            raise ValueError("time_base is required when pts is present")
        fraction = _as_fraction(time_base)
        timestamp_ms = pts_to_ms(pts, fraction, offset_ms=offset_ms)
        discontinuity: Discontinuity | None = None
        if previous is not None:
            if timestamp_ms < previous.timestamp_ms - self.backward_tolerance_ms:
                discontinuity = "backward_pts"
            elif (
                self.max_forward_gap_ms is not None
                and timestamp_ms - previous.end_ms > self.max_forward_gap_ms
            ):
                discontinuity = "forward_gap"

        if discontinuity is not None:
            self.epoch += 1
            self._track_state.clear()
            self._epoch_start_pts = None
            self.last_reset_reason = discontinuity

        if self._epoch_start_pts is None:
            self._epoch_start_pts = pts
        point = ClockPoint(
            stream_id=self.stream_id,
            epoch=self.epoch,
            track_id=track_id,
            pts=pts,
            time_base=fraction,
            timestamp_ms=timestamp_ms,
            duration_ms=duration_ms,
            timestamp_source="pts",
            discontinuity=discontinuity,
        )
        self._track_state[track_id] = _TrackState(
            timestamp_ms=timestamp_ms,
            end_ms=point.end_ms,
            pts=pts,
        )
        return point
