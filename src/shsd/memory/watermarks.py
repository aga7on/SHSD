"""Interval-coverage cursors for progressive capture, embed, draft, and commit stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from threading import RLock
from typing import Literal

CoverageStage = Literal["C", "E", "D", "R"]
CoverageStatus = Literal[
    "pending", "done", "gap", "unavailable", "dropped", "failed", "skipped"
]
Level = Literal["L1", "L2", "L3"]
Modality = Literal["audio", "video", "speech"]

_STAGES: tuple[CoverageStage, ...] = ("C", "E", "D", "R")
_LEVELS: tuple[Level, ...] = ("L1", "L2", "L3")
_MODALITIES = {"audio", "video", "speech"}
_STATUSES: set[str] = {
    "pending",
    "done",
    "gap",
    "unavailable",
    "dropped",
    "failed",
    "skipped",
}
_TERMINAL_STATUSES = {"done", "gap", "unavailable", "dropped", "failed", "skipped"}


class StaleCoverageRevisionError(RuntimeError):
    """A coverage update tried to overwrite a newer interval revision."""


@dataclass(frozen=True, slots=True)
class CoverageSpan:
    stage: CoverageStage
    start_ms: int
    end_ms: int
    status: CoverageStatus
    revision: int
    modality: Modality | None = None
    level: Level | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("coverage interval must satisfy 0 <= start_ms < end_ms")
        if self.revision < 1:
            raise ValueError("coverage revision must be positive")


@dataclass(frozen=True, slots=True)
class CoverageIssue:
    stage: CoverageStage
    start_ms: int
    end_ms: int
    status: CoverageStatus
    modality: Modality | None = None
    level: Level | None = None
    revision: int | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class WatermarkSnapshot:
    stream_id: str
    epoch: int
    C_ms: int
    E_ms: int
    D_ms: dict[Level, int]
    R_ms: dict[Level, int]
    lag_ms: dict[Level, int]
    modality_cursors: dict[Modality, dict[Literal["C", "E"], int]]
    issues: tuple[CoverageIssue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "stream_id": self.stream_id,
            "epoch": self.epoch,
            "C": self.C_ms,
            "E": self.E_ms,
            "D": dict(self.D_ms),
            "R": dict(self.R_ms),
            "lag_ms": dict(self.lag_ms),
            "modality_cursors": {
                modality: dict(cursors) for modality, cursors in self.modality_cursors.items()
            },
            "issues": [asdict(issue) for issue in self.issues],
        }


class WatermarkTracker:
    """Advance cursors only across contiguous coverage or an explicit terminal state."""

    def __init__(
        self,
        stream_id: str,
        *,
        epoch: int = 0,
        required_modalities: set[Modality] | None = None,
        origin_ms: int = 0,
    ) -> None:
        if not stream_id or epoch < 0 or origin_ms < 0:
            raise ValueError("stream_id, non-negative epoch, and origin_ms are required")
        modalities: set[Modality] = (
            set(required_modalities) if required_modalities is not None else {"audio", "video"}
        )
        if not modalities or not modalities.issubset(_MODALITIES):
            raise ValueError("required_modalities must contain audio, video, and/or speech")
        self.stream_id = stream_id
        self.epoch = epoch
        self.required_modalities = frozenset(modalities)
        self.origin_ms = origin_ms
        self._lanes: dict[
            tuple[CoverageStage, Modality | None, Level | None], list[CoverageSpan]
        ] = {}
        self._lock = RLock()

    def begin_epoch(self, epoch: int) -> None:
        """Reset all lane coverage after seek/reconnect; older epoch updates are rejected."""
        with self._lock:
            if epoch <= self.epoch:
                raise ValueError("new epoch must be greater than the current epoch")
            self.epoch = epoch
            self._lanes.clear()

    def mark(
        self,
        stage: CoverageStage,
        start_ms: int,
        end_ms: int,
        status: CoverageStatus,
        *,
        revision: int = 1,
        modality: Modality | None = None,
        level: Level | None = None,
        reason: str | None = None,
        epoch: int | None = None,
    ) -> bool:
        """Record or revise one interval; return false for an exact duplicate update."""
        with self._lock:
            return self._mark_unlocked(
                stage,
                start_ms,
                end_ms,
                status,
                revision=revision,
                modality=modality,
                level=level,
                reason=reason,
                epoch=epoch,
            )

    def _mark_unlocked(
        self,
        stage: CoverageStage,
        start_ms: int,
        end_ms: int,
        status: CoverageStatus,
        *,
        revision: int = 1,
        modality: Modality | None = None,
        level: Level | None = None,
        reason: str | None = None,
        epoch: int | None = None,
    ) -> bool:
        if stage not in _STAGES:
            raise ValueError("stage must be C, E, D, or R")
        if status not in _STATUSES:
            raise ValueError("unsupported coverage status")
        if epoch is not None and epoch != self.epoch:
            raise StaleCoverageRevisionError(
                f"coverage epoch {epoch} is stale; current epoch is {self.epoch}"
            )
        if start_ms < self.origin_ms or end_ms <= start_ms:
            raise ValueError("coverage interval must be within the stream and non-empty")
        if revision < 1:
            raise ValueError("coverage revision must be positive")
        if stage in {"C", "E"}:
            if modality not in self.required_modalities or level is not None:
                raise ValueError("C/E coverage requires a configured modality and no level")
        elif level not in _LEVELS or modality is not None:
            raise ValueError("D/R coverage requires L1/L2/L3 and no modality")

        key = (stage, modality, level)
        current = self._lanes.get(key, [])
        overlaps = [span for span in current if span.start_ms < end_ms and span.end_ms > start_ms]
        for span in overlaps:
            if revision < span.revision:
                raise StaleCoverageRevisionError(
                    f"coverage revision {revision} is older than {span.revision}"
                )
            if revision == span.revision and (status, reason) != (span.status, span.reason):
                raise StaleCoverageRevisionError(
                    "the same interval revision cannot change status or reason"
                )
        if self._already_covered(current, start_ms, end_ms, status, revision, reason):
            return False
        updated = self._overlay(
            current,
            stage,
            start_ms,
            end_ms,
            status,
            revision,
            modality,
            level,
            reason,
        )
        self._lanes[key] = self._merge_adjacent(updated)
        return True

    def spans(
        self,
        stage: CoverageStage,
        *,
        modality: Modality | None = None,
        level: Level | None = None,
    ) -> tuple[CoverageSpan, ...]:
        """Return current non-overlapping coverage spans for one lane."""
        with self._lock:
            return tuple(self._lanes.get((stage, modality, level), ()))

    def mark_revisioned(
        self,
        stage: CoverageStage,
        start_ms: int,
        end_ms: int,
        status: CoverageStatus,
        *,
        modality: Modality | None = None,
        level: Level | None = None,
        reason: str | None = None,
        epoch: int | None = None,
    ) -> bool:
        """Atomically select a revision and mark an interval that may be revised."""
        with self._lock:
            current = self._lanes.get((stage, modality, level), [])
            overlapping = tuple(
                span
                for span in current
                if span.start_ms < end_ms and span.end_ms > start_ms
            )
            if not overlapping:
                revision = 1
            else:
                max_revision = max(span.revision for span in overlapping)
                same_result = all(
                    (span.status, span.reason) == (status, reason)
                    for span in overlapping
                )
                revision = max_revision if same_result else max_revision + 1
            return self._mark_unlocked(
                stage,
                start_ms,
                end_ms,
                status,
                revision=revision,
                modality=modality,
                level=level,
                reason=reason,
                epoch=epoch,
            )

    def mark_uncovered(
        self,
        stage: CoverageStage,
        start_ms: int,
        end_ms: int,
        status: CoverageStatus,
        *,
        modality: Modality | None = None,
        level: Level | None = None,
        reason: str | None = None,
    ) -> None:
        """Fill only uncovered portions of an interval, atomically with other marks."""
        with self._lock:
            if start_ms < self.origin_ms or end_ms <= start_ms:
                raise ValueError("coverage interval must be within the stream and non-empty")
            key = (stage, modality, level)
            cursor = start_ms
            for span in self._lanes.get(key, ()):
                if span.end_ms <= cursor:
                    continue
                if span.start_ms >= end_ms:
                    break
                if span.start_ms > cursor:
                    self._mark_unlocked(
                        stage,
                        cursor,
                        min(end_ms, span.start_ms),
                        status,
                        modality=modality,
                        level=level,
                        reason=reason,
                    )
                cursor = max(cursor, span.end_ms)
                if cursor >= end_ms:
                    break
            if cursor < end_ms:
                self._mark_unlocked(
                    stage,
                    cursor,
                    end_ms,
                    status,
                    modality=modality,
                    level=level,
                    reason=reason,
                )

    def snapshot(self, *, through_ms: int | None = None) -> WatermarkSnapshot:
        """Compute C/E/D/R from contiguous terminal coverage, never max timestamp alone."""
        with self._lock:
            return self._snapshot_unlocked(through_ms=through_ms)

    def _snapshot_unlocked(self, *, through_ms: int | None = None) -> WatermarkSnapshot:
        latest = max(
            (span.end_ms for lane in self._lanes.values() for span in lane),
            default=self.origin_ms,
        )
        target = latest if through_ms is None else through_ms
        if target < self.origin_ms:
            raise ValueError("through_ms must not be before origin_ms")

        modality_cursors: dict[Modality, dict[Literal["C", "E"], int]] = {}
        for modality in sorted(self.required_modalities):
            modality_cursors[modality] = {
                "C": self._contiguous_end(
                    self._lanes.get(("C", modality, None), []), target
                ),
                "E": self._contiguous_end(
                    self._lanes.get(("E", modality, None), []), target
                ),
            }

        capture = min((item["C"] for item in modality_cursors.values()), default=target)
        embedded = min((item["E"] for item in modality_cursors.values()), default=target)
        drafts: dict[Level, int] = {
            level: self._contiguous_end(self._lanes.get(("D", None, level), []), target)
            for level in _LEVELS
        }
        commits: dict[Level, int] = {
            level: self._contiguous_end(self._lanes.get(("R", None, level), []), target)
            for level in _LEVELS
        }
        lag = {level: max(0, capture - commits[level]) for level in _LEVELS}
        issues = self._collect_issues(target)
        return WatermarkSnapshot(
            stream_id=self.stream_id,
            epoch=self.epoch,
            C_ms=capture,
            E_ms=embedded,
            D_ms=drafts,
            R_ms=commits,
            lag_ms=lag,
            modality_cursors=modality_cursors,
            issues=issues,
        )

    def _contiguous_end(self, spans: list[CoverageSpan], target: int) -> int:
        cursor = self.origin_ms
        for span in spans:
            if span.end_ms <= cursor:
                continue
            if span.start_ms > cursor or span.status not in _TERMINAL_STATUSES:
                break
            cursor = min(target, span.end_ms)
            if cursor >= target:
                break
        return cursor

    def _collect_issues(self, target: int) -> tuple[CoverageIssue, ...]:
        result: list[CoverageIssue] = []
        lanes = self._required_lanes()
        for stage, modality, level in lanes:
            spans = self._lanes.get((stage, modality, level), [])
            cursor = self.origin_ms
            for span in spans:
                if span.end_ms <= self.origin_ms or span.start_ms >= target:
                    continue
                start = max(span.start_ms, self.origin_ms)
                end = min(span.end_ms, target)
                if start > cursor:
                    result.append(
                        CoverageIssue(
                            stage,
                            cursor,
                            start,
                            "pending",
                            modality,
                            level,
                            None,
                            "uncovered",
                        )
                    )
                if span.status != "done":
                    result.append(
                        CoverageIssue(
                            stage,
                            start,
                            end,
                            span.status,
                            modality,
                            level,
                            span.revision,
                            span.reason,
                        )
                    )
                cursor = max(cursor, end)
            if cursor < target:
                result.append(
                    CoverageIssue(
                        stage,
                        cursor,
                        target,
                        "pending",
                        modality,
                        level,
                        None,
                        "uncovered",
                    )
                )
        return tuple(result)

    def _required_lanes(
        self,
    ) -> tuple[tuple[CoverageStage, Modality | None, Level | None], ...]:
        modality_stages: tuple[CoverageStage, ...] = ("C", "E")
        level_stages: tuple[CoverageStage, ...] = ("D", "R")
        modalities = tuple(sorted(self.required_modalities))
        modality_lanes: tuple[
            tuple[CoverageStage, Modality | None, Level | None], ...
        ] = tuple(
            (stage, modality, None)
            for stage in modality_stages
            for modality in modalities
        )
        level_lanes: tuple[
            tuple[CoverageStage, Modality | None, Level | None], ...
        ] = tuple(
            (stage, None, level) for stage in level_stages for level in _LEVELS
        )
        return modality_lanes + level_lanes

    @staticmethod
    def _already_covered(
        spans: list[CoverageSpan],
        start_ms: int,
        end_ms: int,
        status: CoverageStatus,
        revision: int,
        reason: str | None,
    ) -> bool:
        cursor = start_ms
        for span in spans:
            if span.end_ms <= cursor:
                continue
            if span.start_ms > cursor:
                return False
            if (span.status, span.revision, span.reason) != (status, revision, reason):
                return False
            cursor = min(end_ms, span.end_ms)
            if cursor >= end_ms:
                return True
        return False

    @staticmethod
    def _overlay(
        spans: list[CoverageSpan],
        stage: CoverageStage,
        start_ms: int,
        end_ms: int,
        status: CoverageStatus,
        revision: int,
        modality: Modality | None,
        level: Level | None,
        reason: str | None,
    ) -> list[CoverageSpan]:
        updated: list[CoverageSpan] = []
        cursor = start_ms
        for span in spans:
            if span.end_ms <= start_ms or span.start_ms >= end_ms:
                updated.append(span)
                continue
            overlap_start = max(start_ms, span.start_ms)
            overlap_end = min(end_ms, span.end_ms)
            if span.start_ms < start_ms:
                updated.append(replace(span, end_ms=start_ms))
            if cursor < overlap_start:
                updated.append(
                    CoverageSpan(
                        stage,
                        cursor,
                        overlap_start,
                        status,
                        revision,
                        modality,
                        level,
                        reason,
                    )
                )
            updated.append(
                CoverageSpan(
                    stage,
                    overlap_start,
                    overlap_end,
                    status,
                    revision,
                    modality,
                    level,
                    reason,
                )
            )
            cursor = overlap_end
            if span.end_ms > end_ms:
                updated.append(replace(span, start_ms=end_ms))
        if cursor < end_ms:
            updated.append(
                CoverageSpan(
                    stage,
                    cursor,
                    end_ms,
                    status,
                    revision,
                    modality,
                    level,
                    reason,
                )
            )
        return sorted(updated, key=lambda span: (span.start_ms, span.end_ms))

    @staticmethod
    def _merge_adjacent(spans: list[CoverageSpan]) -> list[CoverageSpan]:
        merged: list[CoverageSpan] = []
        for span in spans:
            if merged:
                previous = merged[-1]
                previous_state = (
                    previous.stage,
                    previous.status,
                    previous.revision,
                    previous.modality,
                    previous.level,
                    previous.reason,
                )
                current_state = (
                    span.stage,
                    span.status,
                    span.revision,
                    span.modality,
                    span.level,
                    span.reason,
                )
                if (
                    previous.end_ms == span.start_ms
                    and previous_state == current_state
                ):
                    merged[-1] = replace(previous, end_ms=span.end_ms)
                    continue
            merged.append(span)
        return merged
