"""Append-only timeline events and temporal L1 reduction."""

from shsd.memory.models import TimelineClaim, TimelineEvent
from shsd.memory.state import TemporalStateDelta, TemporalStateReducer, TemporalStateSnapshot
from shsd.memory.store import EventStore, StaleRevisionError
from shsd.memory.temporal import TemporalEventReducer, WindowMatch
from shsd.memory.watermarks import (
    CoverageIssue,
    CoverageSpan,
    StaleCoverageRevisionError,
    WatermarkSnapshot,
    WatermarkTracker,
)

__all__ = [
    "EventStore",
    "CoverageIssue",
    "CoverageSpan",
    "StaleRevisionError",
    "StaleCoverageRevisionError",
    "TemporalEventReducer",
    "TemporalStateDelta",
    "TemporalStateReducer",
    "TemporalStateSnapshot",
    "TimelineClaim",
    "TimelineEvent",
    "WindowMatch",
    "WatermarkSnapshot",
    "WatermarkTracker",
]
