"""Independent bounded L1/L2/L3 queues with idempotency and revision-safe writes."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from enum import IntEnum, StrEnum
from threading import RLock
from typing import Literal, Protocol

from shsd.memory.models import TimelineEvent

JobLevel = Literal["L1", "L2", "L3"]
_LEVELS: tuple[JobLevel, ...] = ("L1", "L2", "L3")


class WorkPriority(IntEnum):
    """System-wide order for work classes; lower values are admitted first."""

    CAPTURE = 0
    L0_SIGNAL = 1
    EMBEDDING = 1
    L1 = 2
    L2_ASR = 3
    L3_NARRATION = 4


_LEVEL_PRIORITY = {
    "L1": WorkPriority.L1,
    "L2": WorkPriority.L2_ASR,
    "L3": WorkPriority.L3_NARRATION,
}


@dataclass(frozen=True, slots=True)
class JobKey:
    stream_id: str
    epoch: int
    event_id: str
    revision: int
    level: JobLevel

    def __post_init__(self) -> None:
        if not self.stream_id or not self.event_id:
            raise ValueError("stream_id and event_id are required")
        if self.epoch < 0 or self.revision < 1:
            raise ValueError("epoch must be non-negative and revision must be positive")
        if self.level not in _LEVELS:
            raise ValueError("level must be L1, L2, or L3")


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    key: JobKey
    expected_revision: int
    payload: object
    source_events: tuple[TimelineEvent, ...] = ()

    @property
    def priority(self) -> WorkPriority:
        return _LEVEL_PRIORITY[self.key.level]

    def __post_init__(self) -> None:
        if self.expected_revision < 0:
            raise ValueError("expected_revision must be non-negative")
        if self.key.revision != self.expected_revision + 1:
            raise ValueError("job revision must be expected_revision + 1")
        if self.key.level == "L3" and not self.source_events:
            raise ValueError("L3 narration jobs require one or more stable source events")
        if self.key.level != "L3" and self.source_events:
            raise ValueError("only L3 jobs may batch source events")
        seen: set[tuple[str, int, str, int]] = set()
        for event in self.source_events:
            identity = (event.stream_id, event.epoch, event.event_id, event.revision)
            if identity in seen:
                raise ValueError("L3 source events must be unique")
            seen.add(identity)
            if event.stream_id != self.key.stream_id or event.epoch != self.key.epoch:
                raise ValueError("L3 source events must belong to the job stream and epoch")
            if event.state not in {"refined", "committed"}:
                raise ValueError("L3 may only batch stable refined or committed events")


class SubmitResult(StrEnum):
    QUEUED = "queued"
    DUPLICATE = "duplicate"
    FULL = "full"
    PRESSURE = "pressure"


class LoadMode(StrEnum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    """One decision from the common load-aware admission policy."""

    admitted: bool
    priority: WorkPriority
    mode: LoadMode
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class LoadSample:
    """Bounded runtime signals used to decide which semantic work may proceed."""

    queue_depth: int
    queue_capacity: int
    source_lag_ms: int = 0
    cpu_percent: float = 0.0
    rss_bytes: int = 0
    memory_limit_bytes: int = 0

    def __post_init__(self) -> None:
        if self.queue_depth < 0 or self.queue_capacity < 1:
            raise ValueError("queue depth must be non-negative and capacity positive")
        if self.queue_depth > self.queue_capacity:
            raise ValueError("queue depth cannot exceed its capacity")
        if self.source_lag_ms < 0 or self.rss_bytes < 0 or self.memory_limit_bytes < 0:
            raise ValueError("lag and memory values must be non-negative")
        if not 0 <= self.cpu_percent <= 100:
            raise ValueError("cpu_percent must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class LoadStatus:
    mode: LoadMode
    reasons: tuple[str, ...]
    sample: LoadSample
    recovery_samples: int

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "reasons": list(self.reasons),
            "queue_depth": self.sample.queue_depth,
            "queue_capacity": self.sample.queue_capacity,
            "queue_ratio": round(self.sample.queue_depth / self.sample.queue_capacity, 4),
            "source_lag_ms": self.sample.source_lag_ms,
            "cpu_percent": round(self.sample.cpu_percent, 2),
            "rss_bytes": self.sample.rss_bytes,
            "memory_limit_bytes": self.sample.memory_limit_bytes,
            "recovery_samples": self.recovery_samples,
        }


class RuntimeLoadController:
    """Escalate pressure immediately and require stable samples to recover."""

    def __init__(self, *, recovery_samples: int = 3) -> None:
        if recovery_samples < 1:
            raise ValueError("recovery_samples must be positive")
        self._lock = RLock()
        self._required_recovery_samples = recovery_samples
        self._external_samples: dict[str, LoadSample] = {}
        self._scheduler_samples: dict[str, LoadSample] = {}
        self._mode = LoadMode.NORMAL
        self._recovery_count = 0
        self._status = LoadStatus(
            LoadMode.NORMAL, (), LoadSample(queue_depth=0, queue_capacity=1), 0
        )

    @property
    def status(self) -> LoadStatus:
        with self._lock:
            return self._status

    @property
    def active_source_count(self) -> int:
        """Return registered inputs, including streams still loading their model."""
        with self._lock:
            return len(self._external_samples)

    def register_source(self, source_id: str) -> None:
        """Register a queued stream before capture so shared sampling can adapt early."""
        if not source_id:
            raise ValueError("source_id is required")
        with self._lock:
            self._external_samples.setdefault(
                source_id,
                LoadSample(queue_depth=0, queue_capacity=1),
            )

    @property
    def external_sample(self) -> LoadSample:
        """Aggregate media, embedding, and host observations across sources."""
        with self._lock:
            return self._aggregate_samples(self._external_samples.values())

    def external_sample_for(self, source_id: str = "default") -> LoadSample:
        """Return one source's last media and host resource observation."""
        with self._lock:
            return self._external_samples.get(
                source_id, LoadSample(queue_depth=0, queue_capacity=1)
            )

    def observe(self, sample: LoadSample, *, source_id: str = "default") -> LoadStatus:
        """Update mode from queue, lag, CPU and optional memory pressure."""
        if not source_id:
            raise ValueError("source_id is required")
        with self._lock:
            self._external_samples[source_id] = sample
            return self._observe(self._combined_sample())

    def observe_scheduler(
        self, sample: LoadSample, *, source_id: str = "default"
    ) -> LoadStatus:
        """Merge semantic queue occupancy without erasing ingest pressure."""
        if not source_id:
            raise ValueError("source_id is required")
        with self._lock:
            self._scheduler_samples[source_id] = sample
            return self._observe(self._combined_sample())

    def forget(self, source_id: str) -> LoadStatus:
        """Remove finished source samples so stale pressure cannot affect new work."""
        if not source_id:
            raise ValueError("source_id is required")
        with self._lock:
            existed = self._external_samples.pop(source_id, None) is not None
            existed = self._scheduler_samples.pop(source_id, None) is not None or existed
            if not existed:
                return self._status
            if not self._external_samples and not self._scheduler_samples:
                self._mode = LoadMode.NORMAL
                self._recovery_count = 0
                self._status = LoadStatus(
                    LoadMode.NORMAL,
                    (),
                    LoadSample(queue_depth=0, queue_capacity=1),
                    0,
                )
                return self._status
            return self._observe(self._combined_sample())

    def _combined_sample(self) -> LoadSample:
        external = self._aggregate_samples(self._external_samples.values())
        scheduler = self._aggregate_samples(self._scheduler_samples.values())
        queue_sample = (
            scheduler
            if scheduler.queue_depth / scheduler.queue_capacity
            > external.queue_depth / external.queue_capacity
            else external
        )
        return replace(
            queue_sample,
            source_lag_ms=external.source_lag_ms,
            cpu_percent=external.cpu_percent,
            rss_bytes=external.rss_bytes,
            memory_limit_bytes=external.memory_limit_bytes,
        )

    @staticmethod
    def _aggregate_samples(samples: Iterable[LoadSample]) -> LoadSample:
        values = tuple(samples)
        if not values:
            return LoadSample(queue_depth=0, queue_capacity=1)
        queue_sample = max(
            values,
            key=lambda sample: sample.queue_depth / sample.queue_capacity,
        )
        memory_limits = [
            sample.memory_limit_bytes for sample in values if sample.memory_limit_bytes
        ]
        return replace(
            queue_sample,
            source_lag_ms=max(sample.source_lag_ms for sample in values),
            cpu_percent=max(sample.cpu_percent for sample in values),
            rss_bytes=max(sample.rss_bytes for sample in values),
            memory_limit_bytes=min(memory_limits, default=0),
        )

    def _observe(self, sample: LoadSample) -> LoadStatus:
        ratio = sample.queue_depth / sample.queue_capacity
        memory_ratio = (
            sample.rss_bytes / sample.memory_limit_bytes
            if sample.memory_limit_bytes
            else 0.0
        )
        reasons: list[str] = []
        critical: list[str] = []
        if ratio >= 0.95:
            critical.append("queue_near_capacity")
        if sample.source_lag_ms >= 15_000:
            critical.append("source_lag_critical")
        if sample.cpu_percent >= 95:
            critical.append("cpu_critical")
        if memory_ratio >= 0.90:
            critical.append("memory_critical")
        if ratio >= 0.70:
            reasons.append("queue_pressure")
        if sample.source_lag_ms >= 5_000:
            reasons.append("source_lag_high")
        if sample.cpu_percent >= 85:
            reasons.append("cpu_high")
        if memory_ratio >= 0.80:
            reasons.append("memory_high")

        requested = (
            LoadMode.CRITICAL
            if critical
            else LoadMode.DEGRADED
            if reasons
            else LoadMode.NORMAL
        )
        severity = {LoadMode.NORMAL: 0, LoadMode.DEGRADED: 1, LoadMode.CRITICAL: 2}
        current_severity = severity[self._mode]
        requested_severity = severity[requested]
        if requested_severity > current_severity:
            self._mode = requested
            self._recovery_count = 0
        elif requested_severity < current_severity:
            self._recovery_count += 1
            if self._recovery_count >= self._required_recovery_samples:
                self._mode = requested
                self._recovery_count = 0
        else:
            self._recovery_count = 0

        if requested_severity < current_severity and self._mode is not requested:
            active_reasons = self._status.reasons or tuple(reasons)
        else:
            active_reasons = tuple(reasons)
        self._status = LoadStatus(self._mode, active_reasons, sample, self._recovery_count)
        return self._status

    def permits(self, level: JobLevel) -> bool:
        """Preserve L1 during pressure; defer L2/L3 as they have lower priority."""
        return self.admit(_LEVEL_PRIORITY[level]).admitted

    def permits_priority(self, priority: WorkPriority) -> bool:
        """Keep capture/L0/L1 eligible as pressure rises, then L2, then L3."""
        return self.admit(priority).admitted

    def admit(self, priority: WorkPriority) -> AdmissionDecision:
        """Apply the shared priority policy to any bounded worker lane."""
        with self._lock:
            admitted = (
                self._mode is LoadMode.NORMAL
                or self._mode is LoadMode.DEGRADED
                and priority <= WorkPriority.L2_ASR
                or self._mode is LoadMode.CRITICAL
                and priority <= WorkPriority.L1
            )
            return AdmissionDecision(
                admitted=admitted,
                priority=priority,
                mode=self._mode,
                reason=None if admitted else f"load_{self._mode.value}",
            )


class EventWriter(Protocol):
    """The single append-only logical writer used by all level workers."""

    def append(self, event: TimelineEvent, *, expected_revision: int) -> None: ...


AsyncProcessor = Callable[[ScheduledJob], Awaitable[TimelineEvent]]
ErrorHandler = Callable[[ScheduledJob, Exception], None]
BackpressureHandler = Callable[[ScheduledJob, str], None]


class AsyncLevelScheduler:
    """Bounded queues keep L1 progress independent from slower L2 and L3 work."""

    def __init__(
        self,
        processors: Mapping[JobLevel, AsyncProcessor],
        writer: EventWriter,
        *,
        queue_capacity: int | Mapping[JobLevel, int] = 64,
        dedupe_history: int = 8192,
        on_error: ErrorHandler | None = None,
        on_backpressure: BackpressureHandler | None = None,
        load_controller: RuntimeLoadController | None = None,
        load_source_id: str = "default",
    ) -> None:
        if set(processors) != set(_LEVELS):
            raise ValueError("processors must define L1, L2, and L3")
        if dedupe_history < 1:
            raise ValueError("dedupe_history must be positive")
        capacities = (
            {level: queue_capacity for level in _LEVELS}
            if isinstance(queue_capacity, int)
            else dict(queue_capacity)
        )
        if set(capacities) != set(_LEVELS) or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in capacities.values()
        ):
            raise ValueError("queue capacity must be positive for L1, L2, and L3")
        self._processors = dict(processors)
        self._writer = writer
        self._queues: dict[JobLevel, asyncio.Queue[ScheduledJob | None]] = {
            level: asyncio.Queue(maxsize=capacities[level]) for level in _LEVELS
        }
        self._dedupe_history = dedupe_history
        self._active: set[JobKey] = set()
        self._queued: set[JobKey] = set()
        self._running: set[JobKey] = set()
        self._cancelled: set[JobKey] = set()
        self._completed: set[JobKey] = set()
        self._completed_order: deque[JobKey] = deque()
        self._tasks: list[asyncio.Task[None]] = []
        self._writer_lock = asyncio.Lock()
        self._on_error = on_error
        self._on_backpressure = on_backpressure
        self._load_controller = load_controller or RuntimeLoadController()
        if not load_source_id:
            raise ValueError("load_source_id is required")
        self._load_source_id = load_source_id
        self._queue_capacity = capacities
        self.completed_count = 0
        self.failed_count = 0
        self.cancelled_count = 0
        self.backpressure_count = 0
        self.pressure_rejected_count = 0
        self.last_error: tuple[JobKey, str] | None = None
        self._started = False
        self._closed = False

    def start(self) -> None:
        """Start one isolated worker per level; this does not wait for queued jobs."""
        if self._closed:
            raise RuntimeError("scheduler is closed")
        if self._started:
            return
        self._started = True
        self._tasks = [
            asyncio.create_task(self._run_level(level), name=f"shsd-{level.lower()}-worker")
            for level in _LEVELS
        ]

    def submit(self, job: ScheduledJob) -> SubmitResult:
        """Enqueue without awaiting a model worker or blocking the ingesting task."""
        if not self._started or self._closed:
            raise RuntimeError("scheduler must be started and open before submit")
        key = job.key
        if key in self._active or key in self._completed:
            return SubmitResult.DUPLICATE
        decision = self._load_controller.admit(job.priority)
        if not decision.admitted:
            self.pressure_rejected_count += 1
            self._report_backpressure(job, decision.reason or "load_pressure")
            return SubmitResult.PRESSURE
        queue = self._queues[key.level]
        if queue.full():
            self.backpressure_count += 1
            self._report_backpressure(job, "queue_capacity")
            return SubmitResult.FULL
        queue.put_nowait(job)
        self._active.add(key)
        self._queued.add(key)
        self._refresh_load_status()
        return SubmitResult.QUEUED

    def observe_load(
        self,
        *,
        source_lag_ms: int = 0,
        cpu_percent: float = 0.0,
        rss_bytes: int = 0,
        memory_limit_bytes: int = 0,
    ) -> LoadStatus:
        """Feed measured host/runtime pressure into scheduling admission."""
        external = self._load_controller.external_sample_for(self._load_source_id)
        self._load_controller.observe(
            replace(
                external,
                source_lag_ms=source_lag_ms,
                cpu_percent=cpu_percent,
                rss_bytes=rss_bytes,
                memory_limit_bytes=memory_limit_bytes,
            ),
            source_id=self._load_source_id,
        )
        return self._refresh_load_status()

    def snapshot(self) -> dict[str, object]:
        """Return bounded queue and pressure metrics for API/CLI reporting."""
        queue_depths = {level: self._queues[level].qsize() for level in _LEVELS}
        return {
            "queues": {
                level: {
                    "depth": queue_depths[level],
                    "capacity": self._queue_capacity[level],
                    "outstanding": queue_depths[level]
                    + sum(key.level == level for key in self._running),
                }
                for level in _LEVELS
            },
            "load": self._load_controller.status.to_dict(),
            "backpressure_count": self.backpressure_count,
            "pressure_rejected_count": self.pressure_rejected_count,
            "cancelled_count": self.cancelled_count,
            "failed_count": self.failed_count,
        }

    def cancel(self, key: JobKey) -> bool:
        """Cancel a queued job; in-flight CPU work is left to finish safely."""
        if key not in self._queued:
            return False
        self._cancelled.add(key)
        return True

    async def wait_idle(self) -> None:
        """Wait for all level queues and their current workers to finish."""
        if not self._started:
            return
        await asyncio.gather(*(queue.join() for queue in self._queues.values()))

    async def close(self) -> None:
        """Drain queued work, stop each worker, and prevent further submissions."""
        if self._closed:
            return
        self._closed = True
        if not self._started:
            return
        await self.wait_idle()
        for _level, queue in self._queues.items():
            queue.put_nowait(None)
        await asyncio.gather(*self._tasks)

    async def _run_level(self, level: JobLevel) -> None:
        queue = self._queues[level]
        processor = self._processors[level]
        while True:
            job = await queue.get()
            try:
                if job is None:
                    return
                self._queued.discard(job.key)
                if job.key in self._cancelled:
                    self._cancelled.discard(job.key)
                    self._active.discard(job.key)
                    self.cancelled_count += 1
                    self._remember_completed(job.key)
                    continue
                self._running.add(job.key)
                try:
                    event = await processor(job)
                    self._validate_result(job, event)
                    async with self._writer_lock:
                        self._writer.append(event, expected_revision=job.expected_revision)
                except Exception as error:
                    self.failed_count += 1
                    self.last_error = (job.key, f"{type(error).__name__}: {error}")
                    if self._on_error is not None:
                        try:
                            self._on_error(job, error)
                        except Exception as handler_error:
                            self.last_error = (
                                job.key,
                                f"error handler failed: {type(handler_error).__name__}: "
                                f"{handler_error}",
                            )
                else:
                    self.completed_count += 1
                finally:
                    self._active.discard(job.key)
                    self._running.discard(job.key)
                    self._remember_completed(job.key)
                    self._refresh_load_status()
            finally:
                queue.task_done()

    @staticmethod
    def _validate_result(job: ScheduledJob, event: TimelineEvent) -> None:
        if (event.stream_id, event.epoch, event.event_id, event.revision, event.level) != (
            job.key.stream_id,
            job.key.epoch,
            job.key.event_id,
            job.key.revision,
            job.key.level,
        ):
            raise ValueError("worker result identity and revision must match its scheduled job")

    def _remember_completed(self, key: JobKey) -> None:
        self._completed.add(key)
        self._completed_order.append(key)
        while len(self._completed_order) > self._dedupe_history:
            expired = self._completed_order.popleft()
            self._completed.discard(expired)

    def _refresh_load_status(self) -> LoadStatus:
        queue_states = {
            level: (
                self._queues[level].qsize()
                + sum(key.level == level for key in self._running),
                self._queue_capacity[level] + 1,
            )
            for level in _LEVELS
        }
        pressure_depth, pressure_capacity = max(
            queue_states.values(),
            key=lambda state: state[0] / state[1],
        )
        return self._load_controller.observe_scheduler(
            LoadSample(
                queue_depth=pressure_depth,
                queue_capacity=pressure_capacity,
            ),
            source_id=self._load_source_id,
        )

    def _report_backpressure(self, job: ScheduledJob, reason: str) -> None:
        if self._on_backpressure is None:
            return
        try:
            self._on_backpressure(job, reason)
        except Exception as error:
            self.last_error = (
                job.key,
                f"backpressure handler failed: {type(error).__name__}: {error}",
            )
