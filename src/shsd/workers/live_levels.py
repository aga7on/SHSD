"""Bounded online L2/L3 workers for URL-backed analysis."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from shsd.captions.narrator import CaptionDeduplicator, NarrationRequestDeduplicator
from shsd.memory.models import TimelineEvent
from shsd.memory.state import TemporalStateReducer
from shsd.memory.store import EventStore
from shsd.workers.scheduler import RuntimeLoadController, WorkPriority


@dataclass(frozen=True, slots=True)
class _CoverageBarrier:
    intervals: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class _L2Work:
    event: TimelineEvent
    queued_at: float


@dataclass(frozen=True, slots=True)
class _L3Work:
    event: TimelineEvent
    requests: tuple[Any, ...]
    queued_at: float


class LiveLevelWorkers:
    """Run committed live events through distinct bounded L2 and L3 lanes.

    L1 events must be committed before submission. Coverage barriers are queued
    behind those events so their L2/L3 result cursors cannot outrun queued work.
    """

    def __init__(
        self,
        *,
        store: EventStore,
        load_controller: RuntimeLoadController,
        emit: Callable[[dict[str, Any]], None],
        mark_coverage: Callable[[str, str, int, int, str, str | None], None],
        make_requests: Callable[[list[TimelineEvent]], list[Any]],
        narrator_factory: Callable[[], Any],
        refine_l2: Callable[[TimelineEvent], tuple[TimelineEvent, dict[str, Any]]] | None = None,
        l3_enabled: bool,
        l2_capacity: int = 64,
        l3_capacity: int = 8,
    ) -> None:
        if l2_capacity < 1 or l3_capacity < 1:
            raise ValueError("live level queue capacities must be positive")
        self.store = store
        self.load_controller = load_controller
        self.emit = emit
        self.mark_coverage = mark_coverage
        self.make_requests = make_requests
        self.narrator_factory = narrator_factory
        self.refine_l2 = refine_l2
        self.l3_enabled = l3_enabled
        self.l2_capacity = l2_capacity
        self.l3_capacity = l3_capacity
        self._l2_queue: queue.Queue[_L2Work | _CoverageBarrier | None] = queue.Queue(
            maxsize=l2_capacity
        )
        self._l3_queue: queue.Queue[_L3Work | _CoverageBarrier | None] | None = (
            queue.Queue(maxsize=l3_capacity) if l3_enabled else None
        )
        self._state_reducer = TemporalStateReducer(min_repeats=2)
        self._lock = threading.RLock()
        self._closed = False
        self._l2_running = False
        self._l3_running = False
        self._l2_completed = 0
        self._l2_failed = 0
        self._l2_dropped = 0
        self._l3_completed = 0
        self._l3_deduplicated = 0
        self._l3_failed = 0
        self._l3_dropped = 0
        self._l3_fallbacks = 0
        self._l3_unsupported_claims = 0
        self._narration_backend_counts = {"qwen": 0, "template": 0}
        self._caption_deduplicator = CaptionDeduplicator()
        self._narration_request_deduplicator = NarrationRequestDeduplicator()
        self._l2_latency_ms: list[float] = []
        self._l2_semantic_refinement_counts = {
            "confirmed": 0,
            "abstained": 0,
            "skipped": 0,
        }
        self._l3_latency_ms: list[float] = []
        self._narration_latency_ms: list[float] = []
        self._narration_generation_ms = 0.0
        self._narration_generated_tokens = 0
        self._narration_ranges: list[tuple[int, int]] = []
        self._narration_errors: list[tuple[int, int, str]] = []
        self._l2_skipped_ranges: list[tuple[int, int]] = []
        self._l2_failed_ranges: list[tuple[int, int]] = []
        self._l3_skipped_ranges: list[tuple[int, int]] = []
        self._l3_failed_ranges: list[tuple[int, int]] = []
        self._l2_thread = threading.Thread(target=self._run_l2, name="shsd-live-l2", daemon=True)
        self._l3_thread = (
            threading.Thread(target=self._run_l3, name="shsd-live-l3", daemon=True)
            if l3_enabled
            else None
        )
        self._l2_thread.start()
        if self._l3_thread is not None:
            self._l3_thread.start()

    def queue_loads(self) -> tuple[tuple[int, int], ...]:
        """Return queue depth/capacity samples for the shared load controller."""
        with self._lock:
            l2_running = int(self._l2_running)
            l3_running = int(self._l3_running)
        loads: tuple[tuple[int, int], ...] = (
            (self._l2_queue.qsize() + l2_running, self.l2_capacity + 1),
        )
        if self._l3_queue is not None:
            loads += ((self._l3_queue.qsize() + l3_running, self.l3_capacity + 1),)
        return loads

    def submit_event(self, event: TimelineEvent) -> bool:
        """Queue one stable L0/L1 source event without blocking the media reader."""
        if event.level not in {"L0", "L1"} or event.state != "committed":
            return False
        with self._lock:
            if self._closed:
                return False
        decision = self.load_controller.admit(WorkPriority.L2_ASR)
        if not decision.admitted:
            self._skip_l2(event, decision.reason or "load_pressure")
            return False
        try:
            self._l2_queue.put_nowait(_L2Work(event, time.perf_counter()))
        except queue.Full:
            self._skip_l2(event, "queue_capacity")
            return False
        return True

    def submit_coverage(
        self, intervals: tuple[tuple[int, int], ...], *, block: bool = False
    ) -> bool:
        """Place a coverage barrier after the events already submitted to L2."""
        clean = tuple(
            sorted(
                {(int(start), int(end)) for start, end in intervals if start >= 0 and end > start}
            )
        )
        if not clean:
            return True
        barrier = _CoverageBarrier(clean)
        try:
            if block:
                self._l2_queue.put(barrier)
            else:
                self._l2_queue.put_nowait(barrier)
        except queue.Full:
            return False
        return True

    def finish(self) -> None:
        """Drain L2, then L3, and reject any further submissions."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._l2_queue.put(None)
        self._l2_thread.join()
        if self._l3_thread is not None:
            self._l3_thread.join()

    def snapshot(self) -> dict[str, object]:
        """Report bounded queue state and online completion/latency evidence."""
        with self._lock:
            l2_completed = self._l2_completed
            l2_failed = self._l2_failed
            l2_dropped = self._l2_dropped
            l3_completed = self._l3_completed
            l3_deduplicated = self._l3_deduplicated
            l3_failed = self._l3_failed
            l3_dropped = self._l3_dropped
            narration_ranges = list(self._narration_ranges)
            l3_caption_count = self._l3_completed
            narration_errors = list(self._narration_errors)
            l2_latency = list(self._l2_latency_ms)
            l3_latency = list(self._l3_latency_ms)
            narration_latency = list(self._narration_latency_ms)
            backends = dict(self._narration_backend_counts)
            fallbacks = self._l3_fallbacks
            unsupported = self._l3_unsupported_claims
            tokens = self._narration_generated_tokens
            generation_ms = self._narration_generation_ms
            l2_skipped = list(self._l2_skipped_ranges)
            l2_failed_ranges = list(self._l2_failed_ranges)
            l2_semantic_refinement_counts = dict(self._l2_semantic_refinement_counts)
            l3_skipped = list(self._l3_skipped_ranges)
            l3_failed_ranges = list(self._l3_failed_ranges)
            l2_running = int(self._l2_running)
            l3_running = int(self._l3_running)
        return {
            "queues": {
                "L2": {
                    "depth": self._l2_queue.qsize(),
                    "capacity": self.l2_capacity,
                    "outstanding": self._l2_queue.qsize() + l2_running,
                },
                "L3": {
                    "depth": self._l3_queue.qsize() if self._l3_queue else 0,
                    "capacity": self.l3_capacity if self._l3_queue else 0,
                    "outstanding": (self._l3_queue.qsize() + l3_running if self._l3_queue else 0),
                },
            },
            "completed_count": l2_completed + l3_completed,
            "failed_count": l2_failed + l3_failed,
            "backpressure_count": l2_dropped + l3_dropped,
            "pressure_rejected_count": l2_dropped + l3_dropped,
            "cancelled_count": 0,
            "l2": {
                "completed": l2_completed,
                "failed": l2_failed,
                "dropped": l2_dropped,
                "latency_ms_samples": l2_latency,
                "skipped_ranges": l2_skipped,
                "failed_ranges": l2_failed_ranges,
                "semantic_refinement": {
                    "total": sum(l2_semantic_refinement_counts.values()),
                    **l2_semantic_refinement_counts,
                },
            },
            "l3": {
                "completed": l3_completed,
                "deduplicated": l3_deduplicated,
                "failed": l3_failed,
                "dropped": l3_dropped,
                "latency_ms_samples": l3_latency,
                "skipped_ranges": l3_skipped,
                "failed_ranges": l3_failed_ranges,
            },
            "narration": {
                "caption_count": l3_caption_count,
                "deduplicated_count": l3_deduplicated,
                "ranges": narration_ranges,
                "errors": narration_errors,
                "latency_ms_samples": narration_latency,
                "backend_counts": backends,
                "fallback_count": fallbacks,
                "unsupported_claim_count": unsupported,
                "generated_tokens": tokens or None,
                "generation_ms": round(generation_ms, 3) if generation_ms else None,
                "tokens_per_second": round(tokens / (generation_ms / 1000), 3)
                if generation_ms > 0
                else None,
            },
        }

    def _skip_l2(self, event: TimelineEvent, reason: str) -> None:
        with self._lock:
            self._l2_dropped += 1
            self._l2_skipped_ranges.append((event.start_ms, event.end_ms))
        self.mark_coverage(
            "L2", "D", event.start_ms, event.end_ms, "skipped", "runtime_backpressure"
        )
        self.mark_coverage(
            "L2", "R", event.start_ms, event.end_ms, "skipped", "runtime_backpressure"
        )
        self.emit(
            {
                "record_type": "scheduler_degradation",
                "level": "L2",
                "event_id": event.event_id,
                "reason": reason,
                "load": self.load_controller.status.to_dict(),
            }
        )

    def _skip_l3(self, event: TimelineEvent, reason: str) -> None:
        with self._lock:
            self._l3_dropped += 1
            self._l3_skipped_ranges.append((event.start_ms, event.end_ms))
        self.mark_coverage(
            "L3", "D", event.start_ms, event.end_ms, "skipped", "runtime_backpressure"
        )
        self.mark_coverage(
            "L3", "R", event.start_ms, event.end_ms, "skipped", "runtime_backpressure"
        )
        self.emit(
            {
                "record_type": "scheduler_degradation",
                "level": "L3",
                "event_id": event.event_id,
                "reason": reason,
                "load": self.load_controller.status.to_dict(),
            }
        )

    @staticmethod
    def _intersects(interval: tuple[int, int], ranges: list[tuple[int, int]]) -> bool:
        start_ms, end_ms = interval
        return any(left < end_ms and right > start_ms for left, right in ranges)

    def _run_l2(self) -> None:
        try:
            while True:
                item = self._l2_queue.get()
                try:
                    if item is None:
                        break
                    with self._lock:
                        self._l2_running = True
                    try:
                        if isinstance(item, _CoverageBarrier):
                            self._complete_l2_barrier(item)
                        else:
                            self._process_l2(item)
                    except Exception as error:
                        if isinstance(item, _L2Work):
                            self._record_l2_error(item.event, error)
                        else:
                            self._record_l2_barrier_error(item, error)
                    finally:
                        with self._lock:
                            self._l2_running = False
                finally:
                    self._l2_queue.task_done()
        finally:
            if self._l3_queue is not None:
                self._l3_queue.put(None)

    def _process_l2(self, work: _L2Work) -> None:
        event = work.event
        try:
            refined_source = event
            semantic_report: dict[str, Any] | None = None
            if self.refine_l2 is not None:
                refined_source, semantic_report = self.refine_l2(event)
                if (
                    refined_source.event_id != event.event_id
                    or refined_source.epoch != event.epoch
                    or refined_source.revision != event.revision
                ):
                    raise ValueError(
                        "L2 semantic refinement must preserve event identity and revision"
                    )
                status = str(semantic_report.get("status", "skipped"))
                if status not in self._l2_semantic_refinement_counts:
                    status = "skipped"
                with self._lock:
                    self._l2_semantic_refinement_counts[status] += 1
            delta = self._state_reducer.ingest(refined_source)
            refined = replace(
                refined_source,
                revision=event.revision + 1,
                level="L2",
                state=("refined" if delta is not None and delta.published else "committed"),
                supersedes_revision=event.revision,
                updated_at_utc=datetime.now(UTC).isoformat(),
            )
            self.store.append(refined, expected_revision=event.revision)
        except Exception as error:
            self._record_l2_error(event, error)
            return
        if delta is not None:
            self.emit(
                {
                    "record_type": "state_delta",
                    "level": "L2",
                    "source_event_id": event.event_id,
                    "source_revision": event.revision,
                    **delta.to_dict(),
                }
            )
        if semantic_report is not None:
            self.emit(semantic_report)
        self.emit({"record_type": "event", **refined.to_dict()})
        elapsed_ms = (time.perf_counter() - work.queued_at) * 1000
        with self._lock:
            self._l2_completed += 1
            self._l2_latency_ms.append(elapsed_ms)
        if self._l3_queue is not None:
            try:
                self._submit_l3(refined)
            except Exception as error:
                self._record_narration_error(refined, error)

    def _record_l2_error(self, event: TimelineEvent, error: Exception) -> None:
        message = f"{type(error).__name__}: {error}"[:500]
        with self._lock:
            self._l2_failed += 1
            self._l2_failed_ranges.append((event.start_ms, event.end_ms))
        self.mark_coverage("L2", "R", event.start_ms, event.end_ms, "failed", "l2_worker_failed")
        self.emit(
            {
                "record_type": "scheduler_degradation",
                "level": "L2",
                "event_id": event.event_id,
                "reason": message,
            }
        )

    def _record_l2_barrier_error(self, barrier: _CoverageBarrier, error: Exception) -> None:
        message = f"{type(error).__name__}: {error}"[:500]
        for start_ms, end_ms in barrier.intervals:
            with self._lock:
                self._l2_failed_ranges.append((start_ms, end_ms))
                if self._l3_queue is not None:
                    self._l3_failed_ranges.append((start_ms, end_ms))
            self.mark_coverage("L2", "R", start_ms, end_ms, "failed", "l2_barrier_failed")
            if self._l3_queue is not None:
                self.mark_coverage("L3", "D", start_ms, end_ms, "failed", "l2_barrier_failed")
                self.mark_coverage("L3", "R", start_ms, end_ms, "failed", "l2_barrier_failed")
        self.emit(
            {
                "record_type": "scheduler_degradation",
                "level": "L2",
                "reason": message,
            }
        )

    def _submit_l3(self, event: TimelineEvent) -> None:
        requests = tuple(self.make_requests([event]))
        if not requests:
            self.emit(
                {
                    "record_type": "narration_skipped",
                    "level": "L3",
                    "reason": "no_accepted_claims_with_display_text",
                    "event_revisions": [{"event_id": event.event_id, "revision": event.revision}],
                }
            )
            return
        decision = self.load_controller.admit(WorkPriority.L3_NARRATION)
        if not decision.admitted:
            self._skip_l3(event, decision.reason or "load_pressure")
            return
        assert self._l3_queue is not None
        try:
            self._l3_queue.put_nowait(_L3Work(event, requests, time.perf_counter()))
        except queue.Full:
            self._skip_l3(event, "queue_capacity")

    def _complete_l2_barrier(self, barrier: _CoverageBarrier) -> None:
        with self._lock:
            skipped_ranges = list(self._l2_skipped_ranges)
            failed_ranges = list(self._l2_failed_ranges)
        for start_ms, end_ms in barrier.intervals:
            interval = (start_ms, end_ms)
            if self._intersects(interval, failed_ranges):
                status, reason = "failed", "l2_worker_failed"
            elif self._intersects(interval, skipped_ranges):
                status, reason = "skipped", "runtime_backpressure"
            else:
                status, reason = "done", None
            self.mark_coverage("L2", "R", start_ms, end_ms, status, reason)
        if self._l3_queue is None:
            return
        with self._lock:
            l3_skipped_ranges = list(self._l3_skipped_ranges)
        for start_ms, end_ms in barrier.intervals:
            interval = (start_ms, end_ms)
            if self._intersects(interval, l3_skipped_ranges):
                self.mark_coverage("L3", "D", start_ms, end_ms, "skipped", "runtime_backpressure")
            else:
                self.mark_coverage("L3", "D", start_ms, end_ms, "done", None)
        self._l3_queue.put(barrier)

    def _run_l3(self) -> None:
        assert self._l3_queue is not None
        narrator: Any | None = None
        while True:
            item = self._l3_queue.get()
            try:
                if item is None:
                    return
                with self._lock:
                    self._l3_running = True
                try:
                    if isinstance(item, _CoverageBarrier):
                        self._complete_l3_barrier(item)
                        continue
                    if narrator is None:
                        narrator = self.narrator_factory()
                    for request in item.requests:
                        duplicate_record = self._narration_request_deduplicator.should_skip(request)
                        if duplicate_record is not None:
                            self.emit(duplicate_record)
                            with self._lock:
                                self._l3_deduplicated += 1
                                self._narration_ranges.append(request.time_range)
                            continue
                        try:
                            result = narrator.narrate(request)
                        except Exception as error:
                            self._record_narration_error(item.event, error)
                            continue
                        self._narration_request_deduplicator.remember(
                            request, caption_ru=result.response.caption_ru
                        )
                        record = self._caption_deduplicator.process(result)
                        self.emit(record)
                        response = result.response
                        with self._lock:
                            self._l3_completed += 1
                            self._narration_ranges.append((response.start_ms, response.end_ms))
                            self._narration_latency_ms.append(float(result.latency_ms))
                            self._narration_backend_counts[result.backend] += 1
                            self._l3_fallbacks += result.status == "fallback"
                            self._l3_unsupported_claims += len(response.new_unsupported_claims)
                            if result.generated_token_count is not None and result.generation_ms:
                                self._narration_generated_tokens += result.generated_token_count
                                self._narration_generation_ms += float(result.generation_ms)
                    elapsed_ms = (time.perf_counter() - item.queued_at) * 1000
                    with self._lock:
                        self._l3_latency_ms.append(elapsed_ms)
                finally:
                    with self._lock:
                        self._l3_running = False
            except Exception as error:
                if isinstance(item, _L3Work):
                    self._record_narration_error(item.event, error)
                elif isinstance(item, _CoverageBarrier):
                    self._record_l3_barrier_error(item, error)
            finally:
                self._l3_queue.task_done()

    def _record_l3_barrier_error(self, barrier: _CoverageBarrier, error: Exception) -> None:
        message = f"{type(error).__name__}: {error}"[:500]
        for start_ms, end_ms in barrier.intervals:
            with self._lock:
                self._l3_failed_ranges.append((start_ms, end_ms))
            self.mark_coverage("L3", "R", start_ms, end_ms, "failed", "l3_barrier_failed")
        self.emit(
            {
                "record_type": "scheduler_degradation",
                "level": "L3",
                "reason": message,
            }
        )

    def _record_narration_error(self, event: TimelineEvent, error: Exception) -> None:
        message = f"{type(error).__name__}: {error}"[:500]
        with self._lock:
            self._l3_failed += 1
            self._l3_failed_ranges.append((event.start_ms, event.end_ms))
            self._narration_errors.append((event.start_ms, event.end_ms, message))
        self.mark_coverage("L3", "R", event.start_ms, event.end_ms, "failed", "narration_failed")
        self.emit(
            {
                "record_type": "narration_error",
                "level": "L3",
                "time_range": {"start_ms": event.start_ms, "end_ms": event.end_ms},
                "error": message,
                "event_revisions": [{"event_id": event.event_id, "revision": event.revision}],
            }
        )

    def _complete_l3_barrier(self, barrier: _CoverageBarrier) -> None:
        with self._lock:
            skipped_ranges = list(self._l3_skipped_ranges)
            failed_ranges = list(self._l3_failed_ranges)
        for start_ms, end_ms in barrier.intervals:
            interval = (start_ms, end_ms)
            if self._intersects(interval, failed_ranges):
                status, reason = "failed", "narration_failed"
            elif self._intersects(interval, skipped_ranges):
                status, reason = "skipped", "runtime_backpressure"
            else:
                status, reason = "done", None
            self.mark_coverage("L3", "R", start_ms, end_ms, status, reason)
