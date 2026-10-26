"""Bounded serial worker for L1 semantic matching and temporal reduction."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from shsd.workers.scheduler import RuntimeLoadController, WorkPriority


@dataclass(frozen=True, slots=True)
class L1Work:
    """One ordered L1 operation owned by the worker thread."""

    job_id: int
    run: Callable[[], None]


class BoundedL1Worker:
    """Keep L1 scoring and reducer mutations off the media consumer thread."""

    def __init__(
        self,
        *,
        queue_capacity: int = 4,
        load_controller: RuntimeLoadController | None = None,
    ) -> None:
        if queue_capacity < 1:
            raise ValueError("L1 queue capacity must be positive")
        self._load_controller = load_controller
        self.queue_capacity = queue_capacity
        self._tasks: queue.Queue[L1Work | None] = queue.Queue(maxsize=queue_capacity)
        self._slots = threading.BoundedSemaphore(queue_capacity)
        self._condition = threading.Condition()
        self._thread = threading.Thread(target=self._run, name="shsd-l1", daemon=True)
        self._closed = False
        self.outstanding = 0
        self.submitted_count = 0
        self.completed_count = 0
        self.failed_count = 0
        self.max_outstanding = 0
        self.total_work_ms = 0.0
        self.last_error: str | None = None
        self._first_error: tuple[int, Exception] | None = None
        self._thread.start()

    def submit(self, work: L1Work) -> None:
        """Queue in timestamp order, applying bounded backpressure when full."""
        if self._load_controller is not None:
            decision = self._load_controller.admit(WorkPriority.L1)
            if not decision.admitted:
                raise RuntimeError(
                    f"L1 job {work.job_id} rejected: {decision.reason or 'load_pressure'}"
                )
        while not self._slots.acquire(timeout=0.01):
            with self._condition:
                if self._closed:
                    raise RuntimeError("L1 worker is closed")
        with self._condition:
            if self._closed:
                self._slots.release()
                raise RuntimeError("L1 worker is closed")
            self.outstanding += 1
            self.submitted_count += 1
            self.max_outstanding = max(self.max_outstanding, self.outstanding)
        try:
            self._tasks.put_nowait(work)
        except Exception:
            with self._condition:
                self.outstanding -= 1
                self._condition.notify_all()
            self._slots.release()
            raise

    def wait_idle(self) -> None:
        """Wait until all submitted work has completed, then surface its first error."""
        with self._condition:
            while self.outstanding:
                self._condition.wait(timeout=0.05)
            error = self._first_error
            self._first_error = None
        if error is not None:
            job_id, cause = error
            message = f"L1 job {job_id} failed: {type(cause).__name__}: {cause}"
            raise RuntimeError(message) from cause

    def finish(self) -> None:
        """Drain the lane and stop its thread."""
        if self._closed:
            return
        first_error: Exception | None = None
        try:
            self.wait_idle()
        except Exception as error:
            first_error = error
        with self._condition:
            self._closed = True
        self._tasks.put_nowait(None)
        self._thread.join()
        if first_error is not None:
            raise first_error

    def snapshot(self) -> dict[str, int | float | str | None]:
        """Return bounded lane counters for the stream metrics row."""
        with self._condition:
            return {
                "queue_capacity": self.queue_capacity,
                "queue_depth": self._tasks.qsize(),
                "outstanding": self.outstanding,
                "submitted": self.submitted_count,
                "completed": self.completed_count,
                "failed": self.failed_count,
                "max_outstanding": self.max_outstanding,
                "total_work_ms": round(self.total_work_ms, 3),
                "last_error": self.last_error,
            }

    def _run(self) -> None:
        while True:
            work = self._tasks.get()
            if work is None:
                self._tasks.task_done()
                return
            started = time.perf_counter()
            error: Exception | None = None
            try:
                work.run()
            except Exception as caught:
                error = caught
            elapsed_ms = (time.perf_counter() - started) * 1000
            with self._condition:
                self.total_work_ms += elapsed_ms
                if error is None:
                    self.completed_count += 1
                else:
                    self.failed_count += 1
                    self.last_error = f"{type(error).__name__}: {error}"[:500]
                    if self._first_error is None:
                        self._first_error = (work.job_id, error)
                self.outstanding -= 1
                self._condition.notify_all()
            self._slots.release()
            self._tasks.task_done()
