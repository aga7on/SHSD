"""Bounded serial inference worker for audio and image embeddings."""

from __future__ import annotations

import queue
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from shsd.embeddings.provider import EmbeddingRecord
from shsd.workers.scheduler import RuntimeLoadController, WorkPriority


@dataclass(frozen=True, slots=True)
class EmbeddingJob:
    """One inference closure submitted in media timestamp order."""

    job_id: int
    encode: Callable[[], EmbeddingRecord]


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Inference output; elapsed includes provider contention, inference does not."""

    job_id: int
    record: EmbeddingRecord | None
    elapsed_ms: float
    inference_ms: float
    queue_wait_ms: float = 0.0
    modality: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _QueuedEmbeddingJob:
    job: EmbeddingJob
    submitted_at: float


@dataclass(frozen=True, slots=True)
class _ScheduledEmbeddingJob:
    source_id: str
    job: EmbeddingJob
    submitted_at: float
    result_sink: Callable[[EmbeddingResult], None]


ResultHandler = Callable[[EmbeddingResult], None]


class SharedEmbeddingDispatcher:
    """Bounded round-robin inference queue shared by streams using one provider."""

    def __init__(
        self,
        *,
        queue_capacity: int = 64,
        worker_count: int = 1,
        source_stats_capacity: int = 256,
    ) -> None:
        if queue_capacity < 1:
            raise ValueError("shared embedding queue capacity must be positive")
        if worker_count < 1:
            raise ValueError("shared embedding worker count must be positive")
        if source_stats_capacity < 1:
            raise ValueError("source stats capacity must be positive")
        self.queue_capacity = queue_capacity
        self.worker_count = worker_count
        self.source_stats_capacity = source_stats_capacity
        self._condition = threading.Condition()
        self._queues: dict[str, deque[_ScheduledEmbeddingJob]] = {}
        self._rotation: deque[str] = deque()
        self._pending = 0
        self._active_sources: set[str] = set()
        self._closing = False
        self._threads = [
            threading.Thread(
                target=self._run,
                name=f"shsd-shared-embedding-{index + 1}",
                daemon=True,
            )
            for index in range(worker_count)
        ]
        # Keep the first worker attribute for existing lifecycle diagnostics.
        self._thread = self._threads[0]
        self._peak_pending = 0
        self._peak_active = 0
        self._dispatched_count = 0
        self._total_queue_wait_ms = 0.0
        self._total_inference_ms = 0.0
        self._per_source: OrderedDict[str, dict[str, int | float]] = OrderedDict()
        self._sink_error_count = 0
        for thread in self._threads:
            thread.start()

    def try_submit(
        self,
        source_id: str,
        job: EmbeddingJob,
        result_sink: Callable[[EmbeddingResult], None],
    ) -> bool:
        """Enqueue one job, returning false when the global bounded queue is full."""
        if not source_id:
            raise ValueError("source_id is required for shared embedding dispatch")
        with self._condition:
            if self._closing:
                raise RuntimeError("shared embedding dispatcher is closing")
            if self._pending >= self.queue_capacity:
                return False
            per_source = self._queues.get(source_id)
            if per_source is None:
                per_source = deque()
                self._queues[source_id] = per_source
                self._rotation.append(source_id)
            per_source.append(
                _ScheduledEmbeddingJob(
                    source_id=source_id,
                    job=job,
                    submitted_at=time.perf_counter(),
                    result_sink=result_sink,
                )
            )
            self._pending += 1
            self._peak_pending = max(self._peak_pending, self._pending)
            self._condition.notify()
            return True

    def wait_for_space(self, timeout: float = 0.01) -> bool:
        """Wait briefly for one pending slot; return false on timeout."""
        with self._condition:
            if self._closing:
                raise RuntimeError("shared embedding dispatcher is closing")
            return self._condition.wait_for(
                lambda: self._pending < self.queue_capacity or self._closing,
                timeout=timeout,
            ) and not self._closing

    def snapshot(self) -> dict[str, Any]:
        """Return queue depth and bounded per-source service counters."""
        with self._condition:
            return {
                "queue_capacity": self.queue_capacity,
                "worker_count": self.worker_count,
                "source_stats_capacity": self.source_stats_capacity,
                "queue_depth": self._pending,
                "peak_queue_depth": self._peak_pending,
                "active_source": (
                    next(iter(self._active_sources))
                    if len(self._active_sources) == 1
                    else None
                ),
                "active_sources": sorted(self._active_sources),
                "active_count": len(self._active_sources),
                "peak_active": self._peak_active,
                "source_count": len(self._queues),
                "dispatched_count": self._dispatched_count,
                "result_sink_errors": self._sink_error_count,
                "total_queue_wait_ms": round(self._total_queue_wait_ms, 3),
                "total_inference_ms": round(self._total_inference_ms, 3),
                "by_source": {
                    source_id: {
                        key: round(value, 3) if isinstance(value, float) else value
                        for key, value in metrics.items()
                    }
                    for source_id, metrics in sorted(self._per_source.items())
                },
            }

    def close(self, *, timeout: float | None = None) -> None:
        """Stop accepting jobs, drain queued work, and join the dispatch thread."""
        with self._condition:
            self._closing = True
            self._condition.notify_all()
        deadline = None if timeout is None else time.monotonic() + timeout
        for thread in self._threads:
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            thread.join(timeout=remaining)
        if any(thread.is_alive() for thread in self._threads):
            raise TimeoutError("shared embedding dispatcher did not drain before timeout")

    def _run(self) -> None:
        while True:
            with self._condition:
                scheduled: _ScheduledEmbeddingJob | None = None
                source_id: str | None = None
                while scheduled is None:
                    if self._pending == 0 and self._closing:
                        return
                    for _ in range(len(self._rotation)):
                        candidate = self._rotation.popleft()
                        per_source = self._queues[candidate]
                        if candidate in self._active_sources:
                            self._rotation.append(candidate)
                            continue
                        source_id = candidate
                        scheduled = per_source.popleft()
                        self._pending -= 1
                        self._active_sources.add(candidate)
                        self._peak_active = max(
                            self._peak_active, len(self._active_sources)
                        )
                        if per_source:
                            self._rotation.append(candidate)
                        else:
                            del self._queues[candidate]
                        self._condition.notify_all()
                        break
                    if scheduled is None:
                        self._condition.wait()

            assert source_id is not None

            result = _execute_embedding_job(
                scheduled.job,
                submitted_at=scheduled.submitted_at,
            )
            sink_failed = False
            try:
                scheduled.result_sink(result)
            except Exception:
                # A faulty consumer callback must not silently kill the shared worker.
                sink_failed = True
            finally:
                with self._condition:
                    self._active_sources.remove(source_id)
                    self._dispatched_count += 1
                    self._sink_error_count += int(sink_failed)
                    self._total_queue_wait_ms += result.queue_wait_ms
                    self._total_inference_ms += result.inference_ms
                    metrics = self._per_source.get(source_id)
                    if metrics is None:
                        if len(self._per_source) >= self.source_stats_capacity:
                            self._per_source.popitem(last=False)
                        metrics = {
                            "dispatched": 0,
                            "failed": 0,
                            "queue_wait_ms": 0.0,
                            "inference_ms": 0.0,
                        }
                        self._per_source[source_id] = metrics
                    else:
                        self._per_source.move_to_end(source_id)
                    metrics["dispatched"] = int(metrics["dispatched"]) + 1
                    metrics["failed"] = int(metrics["failed"]) + int(result.error is not None)
                    metrics["queue_wait_ms"] = (
                        float(metrics["queue_wait_ms"]) + result.queue_wait_ms
                    )
                    metrics["inference_ms"] = (
                        float(metrics["inference_ms"]) + result.inference_ms
                    )
                    self._condition.notify_all()


def _execute_embedding_job(
    job: EmbeddingJob,
    *,
    submitted_at: float,
) -> EmbeddingResult:
    started = time.perf_counter()
    try:
        record = job.encode()
    except Exception as error:
        return EmbeddingResult(
            job_id=job.job_id,
            record=None,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            inference_ms=0.0,
            queue_wait_ms=(started - submitted_at) * 1000,
            error=f"{type(error).__name__}: {error}"[:500],
        )
    return EmbeddingResult(
        job_id=job.job_id,
        record=record,
        elapsed_ms=(time.perf_counter() - started) * 1000,
        inference_ms=0.0 if record.cache_hit else record.latency_ms,
        queue_wait_ms=(started - submitted_at) * 1000,
        modality=record.modality,
    )


class BoundedEmbeddingWorker:
    """Run model inference serially while the caller continues cheap media work.

    Results are consumed by the caller thread. This keeps EventStore and temporal
    reducer mutations on their owning thread while preserving submission order.
    """

    def __init__(
        self,
        *,
        queue_capacity: int = 2,
        load_controller: RuntimeLoadController | None = None,
        shared_dispatcher: SharedEmbeddingDispatcher | None = None,
        source_id: str = "default",
    ) -> None:
        if queue_capacity < 1:
            raise ValueError("embedding queue capacity must be positive")
        self._load_controller = load_controller
        if not source_id:
            raise ValueError("source_id is required")
        self._shared_dispatcher = shared_dispatcher
        self._source_id = source_id
        self.queue_capacity = queue_capacity
        self._tasks: queue.Queue[_QueuedEmbeddingJob | None] = queue.Queue(
            maxsize=queue_capacity
        )
        self._results: queue.Queue[EmbeddingResult] = queue.Queue(maxsize=queue_capacity)
        self._slots = threading.BoundedSemaphore(queue_capacity)
        self._closed = False
        self.outstanding = 0
        self.submitted_count = 0
        self.completed_count = 0
        self.failed_count = 0
        self.max_outstanding = 0
        self.total_inference_ms = 0.0
        self.total_worker_elapsed_ms = 0.0
        self.total_queue_wait_ms = 0.0
        self._by_modality: dict[str, dict[str, int | float]] = {}
        self._results_ready = threading.Event()
        self._thread: threading.Thread | None = None
        if shared_dispatcher is None:
            self._thread = threading.Thread(
                target=self._run,
                name="shsd-embedding",
                daemon=True,
            )
            self._thread.start()

    def submit(self, job: EmbeddingJob, handler: ResultHandler) -> None:
        """Queue work, draining completed results whenever bounded slots fill."""
        if self._closed:
            raise RuntimeError("embedding worker is closed")
        if self._load_controller is not None:
            decision = self._load_controller.admit(WorkPriority.EMBEDDING)
            if not decision.admitted:
                raise RuntimeError(
                    f"embedding job {job.job_id} rejected: {decision.reason or 'load_pressure'}"
                )
        while not self._slots.acquire(timeout=0.01):
            self.drain(handler)
            if self._closed:
                raise RuntimeError("embedding worker is closed")
        if self._closed:
            self._slots.release()
            raise RuntimeError("embedding worker is closed")
        try:
            if self._shared_dispatcher is None:
                self._tasks.put_nowait(
                    _QueuedEmbeddingJob(job=job, submitted_at=time.perf_counter())
                )
            else:
                while not self._shared_dispatcher.try_submit(
                    self._source_id,
                    job,
                    self._enqueue_result,
                ):
                    self.drain(handler)
                    if self._closed:
                        raise RuntimeError("embedding worker is closed")
                    self._shared_dispatcher.wait_for_space()
        except Exception:
            self._slots.release()
            raise
        self.outstanding += 1
        self.submitted_count += 1
        self.max_outstanding = max(self.max_outstanding, self.outstanding)

    def drain(self, handler: ResultHandler) -> int:
        """Apply all currently completed results on the caller thread."""
        count = 0
        first_error: Exception | None = None
        while True:
            try:
                result = self._results.get_nowait()
            except queue.Empty:
                break
            self.outstanding -= 1
            self.total_worker_elapsed_ms += result.elapsed_ms
            self.total_inference_ms += result.inference_ms
            self.total_queue_wait_ms += result.queue_wait_ms
            if result.error is None:
                self.completed_count += 1
            else:
                self.failed_count += 1
            if result.modality is not None:
                modality_metrics = self._by_modality.setdefault(
                    result.modality,
                    {
                        "completed": 0,
                        "failed": 0,
                        "cache_hits": 0,
                        "queue_wait_ms": 0.0,
                        "worker_elapsed_ms": 0.0,
                        "inference_ms": 0.0,
                    },
                )
                modality_metrics["completed"] = int(modality_metrics["completed"]) + (
                    result.error is None
                )
                modality_metrics["failed"] = int(modality_metrics["failed"]) + (
                    result.error is not None
                )
                modality_metrics["cache_hits"] = int(modality_metrics["cache_hits"]) + int(
                    result.record is not None and result.record.cache_hit
                )
                modality_metrics["queue_wait_ms"] = (
                    float(modality_metrics["queue_wait_ms"]) + result.queue_wait_ms
                )
                modality_metrics["worker_elapsed_ms"] = (
                    float(modality_metrics["worker_elapsed_ms"]) + result.elapsed_ms
                )
                modality_metrics["inference_ms"] = (
                    float(modality_metrics["inference_ms"]) + result.inference_ms
                )
            self._slots.release()
            try:
                handler(result)
            except Exception as error:
                if first_error is None:
                    first_error = error
            count += 1
        if first_error is not None:
            raise first_error
        self._results_ready.clear()
        if not self._results.empty():
            self._results_ready.set()
        return count

    def wait_idle(self, handler: ResultHandler) -> None:
        """Drain every submitted job before an ordered main-thread reducer action."""
        first_error: Exception | None = None
        while self.outstanding:
            try:
                self.drain(handler)
            except Exception as error:
                if first_error is None:
                    first_error = error
            if self.outstanding:
                self._results_ready.wait(timeout=0.01)
        if first_error is not None:
            raise first_error

    def finish(self, handler: ResultHandler) -> None:
        """Drain work and stop the worker without leaving queued results behind."""
        if self._closed:
            return
        self._closed = True
        first_error: Exception | None = None
        while self.outstanding:
            try:
                self.drain(handler)
            except Exception as error:
                if first_error is None:
                    first_error = error
            if self.outstanding:
                self._results_ready.wait(timeout=0.01)
        if self._thread is not None:
            self._tasks.put_nowait(None)
            self._thread.join()
        if first_error is not None:
            raise first_error

    def snapshot(self) -> dict[str, Any]:
        """Return bounded worker counters for analysis metrics."""
        return {
            "queue_capacity": self.queue_capacity,
            "submitted": self.submitted_count,
            "completed": self.completed_count,
            "failed": self.failed_count,
            "max_outstanding": self.max_outstanding,
            "source_id": self._source_id,
            "total_queue_wait_ms": round(self.total_queue_wait_ms, 3),
            "total_inference_ms": round(self.total_inference_ms, 3),
            "total_worker_elapsed_ms": round(self.total_worker_elapsed_ms, 3),
            "by_modality": {
                modality: {
                    key: round(value, 3) if isinstance(value, float) else value
                    for key, value in metrics.items()
                }
                for modality, metrics in sorted(self._by_modality.items())
            },
        }

    def _enqueue_result(self, result: EmbeddingResult) -> None:
        self._results.put(result)
        self._results_ready.set()

    def _run(self) -> None:
        while True:
            task = self._tasks.get()
            if task is None:
                self._tasks.task_done()
                return
            result = _execute_embedding_job(
                task.job,
                submitted_at=task.submitted_at,
            )
            self._enqueue_result(result)
            self._tasks.task_done()
