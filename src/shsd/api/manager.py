"""In-process stream jobs, revision publication, and websocket replay support."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import uuid
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock
from typing import Any, Literal, cast
from urllib.parse import urlsplit, urlunsplit

from shsd.analyze import _narration_batches, analyze_media
from shsd.embeddings.provider import EmbeddingProviderPool
from shsd.ingest.live import LiveSourceInterruptedError
from shsd.ingest.prefetch import OverflowPolicy
from shsd.memory import EventStore, TemporalStateReducer, WatermarkTracker
from shsd.memory.watermarks import CoverageStage, Level, Modality
from shsd.semantic.matcher import MatchPolicy
from shsd.workers.scheduler import RuntimeLoadController

StreamStatus = Literal["queued", "running", "stopping", "stopped", "completed", "failed"]
StreamLevel = Literal["L0", "L1", "L2", "L3"]
RefineLevel = Literal["L2", "L3"]
MESSAGE_TYPES = {
    "stream.created",
    "stream.started",
    "stream.stopping",
    "stream.reconnecting",
    "stream.stopped",
    "stream.completed",
    "stream.watermarks.changed",
    "stream.event.created",
    "stream.event.revised",
    "stream.event.committed",
    "stream.caption.ready",
    "stream.gap_detected",
    "stream.error",
    "stream.refine.queued",
    "stream.refine.started",
    "stream.refine.completed",
}
_STREAM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_LIVE_RECONNECT_MAX_ATTEMPTS = 5
_LIVE_RECONNECT_INITIAL_DELAY_SECONDS = 0.5
_LIVE_RECONNECT_MAX_DELAY_SECONDS = 8.0
_LOGGER = logging.getLogger(__name__)
_METADATA_PERSISTENCE_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="shsd-session-metadata",
)


def _source_label(source: str | Path) -> str:
    """Remove URL credentials and query tokens from persisted and public fields."""
    if not isinstance(source, str) or "://" not in source:
        return str(source)
    try:
        parts = urlsplit(source)
        hostname = parts.hostname
        if hostname is None:
            return f"{parts.scheme}://[redacted]"
        if ":" in hostname:
            hostname = f"[{hostname}]"
        port = f":{parts.port}" if parts.port is not None else ""
        return urlunsplit((parts.scheme, f"{hostname}{port}", parts.path, "", ""))
    except ValueError:
        return "[redacted URL]"


def _restore_source(source: str) -> str | Path:
    """Keep sanitized URLs as strings; local paths retain Path semantics."""
    return source if "://" in source else Path(source)


def _is_live_source(source: str | Path) -> bool:
    return isinstance(source, str) and urlsplit(source).scheme.lower() in {"rtsp", "rtsps"}


def _safe_error(source: str | Path, error: BaseException) -> str:
    """Avoid copying URL credentials or query tokens into stream error records."""
    message = str(error)
    if isinstance(source, str) and "://" in source:
        parts = urlsplit(source)
        message = message.replace(source, _source_label(source))
        if "@" in parts.netloc:
            message = message.replace(parts.netloc, _source_label(source).split("//", 1)[-1])
        if parts.query:
            message = message.replace(parts.query, "[redacted query]")
    return f"{type(error).__name__}: {message}"[:1_000]


def _metadata_int(metadata: dict[str, object], name: str, default: int) -> int:
    value = metadata.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _metadata_float(metadata: dict[str, object], name: str, default: float) -> float:
    value = metadata.get(name)
    return (
        float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default
    )


def _metadata_dict(metadata: dict[str, object], name: str) -> dict[str, Any] | None:
    value = metadata.get(name)
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


@dataclass(slots=True)
class StreamSession:
    stream_id: str
    source: str | Path
    database_path: Path
    levels: tuple[StreamLevel, ...]
    threads: int
    window_ms: int
    minimum_similarity: float
    minimum_margin: float
    top_k: int
    created_at_utc: str
    stop_event: Event = field(default_factory=Event, repr=False)
    speech_enabled: bool = False
    sampling_profile: Literal["standard", "adaptive"] = "standard"
    vision_profile: Literal["standard", "compact"] = "standard"
    prefetch_overflow_policy: OverflowPolicy = "block"
    prefetch_capacity: int | None = None
    status: StreamStatus = "queued"
    epoch: int = 0
    source_duration_ms: int | None = None
    modalities: dict[str, Any] | None = None
    watermarks: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    error: str | None = None
    sequence: int = 0
    journal: deque[dict[str, Any]] = field(default_factory=deque)
    subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)
    event_heads: dict[str, int] = field(default_factory=dict)
    gap_signatures: set[tuple[Any, ...]] = field(default_factory=set)
    refine_jobs: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class RefineWork:
    session: StreamSession
    level: RefineLevel
    start_ms: int
    end_ms: int
    job_ids: list[str]
    sequence: int


class RefineQueueFullError(RuntimeError):
    """Raised when the bounded post-analysis refinement queue is saturated."""


AnalysisRunner = Callable[..., dict[str, Any]]


class StreamManager:
    """Run bounded file or URL analyses and expose replayable stream events."""

    def __init__(
        self,
        *,
        root: Path,
        data_dir: Path,
        models_dir: Path | None = None,
        cache_dir: Path | None = None,
        embedding_concurrency: int = 1,
        analysis_runner: AnalysisRunner | None = None,
        load_controller: RuntimeLoadController | None = None,
        embedding_provider_pool: EmbeddingProviderPool | None = None,
        journal_limit: int = 2_048,
        subscriber_queue_size: int = 256,
        refine_queue_capacity: int = 32,
        refine_merge_window_ms: int = 0,
    ) -> None:
        if journal_limit < 2 or subscriber_queue_size < 2 or refine_queue_capacity < 1:
            raise ValueError(
                "journal/subscriber limits must be at least two and refine capacity positive"
            )
        if refine_merge_window_ms < 0:
            raise ValueError("refine_merge_window_ms must be non-negative")
        if embedding_concurrency < 1:
            raise ValueError("embedding_concurrency must be positive")
        self.root = root.resolve()
        self.models_dir = (models_dir or self.root / "models").resolve()
        self.cache_dir = cache_dir
        self.data_dir = data_dir.resolve()
        self.models_lock = json.loads((self.root / "models.lock.json").read_text(encoding="utf-8"))
        self.analysis_runner = analysis_runner or analyze_media
        self.load_controller = load_controller or RuntimeLoadController()
        self.embedding_provider_pool = embedding_provider_pool or EmbeddingProviderPool(
            inference_concurrency=embedding_concurrency
        )
        self.journal_limit = journal_limit
        self.subscriber_queue_size = subscriber_queue_size
        self._analysis_tasks: set[asyncio.Task[None]] = set()
        self.refine_merge_window_ms = refine_merge_window_ms
        self._streams: dict[str, StreamSession] = {}
        self._refine_queue: asyncio.PriorityQueue[tuple[int, int, RefineWork]] = (
            asyncio.PriorityQueue(maxsize=refine_queue_capacity)
        )
        self._refine_pending: list[RefineWork] = []
        self._refine_sequence = 0
        self._refine_dispatch_task: asyncio.Task[None] | None = None
        self._metadata_persistence_guard = Lock()
        self._metadata_persistence_locks: dict[str, Lock] = {}
        self._metadata_persistence_pending: dict[str, StreamSession] = {}
        self._metadata_persistence_worker_running = False
        self._metadata_persistence_idle: dict[str, Event] = {}
        self._metadata_persistence_coalesced: dict[str, int] = {}
        self._restore_sessions()

    def _session_metadata(self, session: StreamSession) -> dict[str, object]:
        return {
            "stream_id": session.stream_id,
            "source": _source_label(session.source),
            "levels": list(session.levels),
            "threads": session.threads,
            "window_ms": session.window_ms,
            "minimum_similarity": session.minimum_similarity,
            "minimum_margin": session.minimum_margin,
            "top_k": session.top_k,
            "speech_enabled": session.speech_enabled,
            "sampling_profile": session.sampling_profile,
            "vision_profile": session.vision_profile,
            "prefetch_overflow_policy": session.prefetch_overflow_policy,
            "prefetch_capacity": session.prefetch_capacity,
            "created_at_utc": session.created_at_utc,
            "status": session.status,
            "epoch": session.epoch,
            "source_duration_ms": session.source_duration_ms,
            "modalities": session.modalities,
            "watermarks": session.watermarks,
            "metrics": session.metrics,
            "error": session.error,
            "refine_jobs": list(session.refine_jobs.values()),
        }

    def _persist_session(self, session: StreamSession) -> None:
        with self._metadata_persistence_lock(session.stream_id):
            with EventStore(session.database_path) as store:
                store.save_stream_metadata(session.stream_id, self._session_metadata(session))

    def _metadata_persistence_lock(self, stream_id: str) -> Lock:
        with self._metadata_persistence_guard:
            return self._metadata_persistence_locks.setdefault(stream_id, Lock())

    def _schedule_session_persist(self, session: StreamSession) -> None:
        """Persist the newest session snapshot off-loop, coalescing intermediate updates."""
        worker_started = False
        stream_id = session.stream_id
        with self._metadata_persistence_guard:
            idle = self._metadata_persistence_idle.setdefault(stream_id, Event())
            idle.clear()
            if stream_id in self._metadata_persistence_pending:
                self._metadata_persistence_coalesced[stream_id] = (
                    self._metadata_persistence_coalesced.get(stream_id, 0) + 1
                )
            self._metadata_persistence_pending[stream_id] = session
            if not self._metadata_persistence_worker_running:
                self._metadata_persistence_worker_running = True
                worker_started = True
        if worker_started:
            _METADATA_PERSISTENCE_EXECUTOR.submit(self._drain_session_persistence)

    def _wait_for_session_persistence(
        self, session: StreamSession, timeout: float | None = None
    ) -> bool:
        """Wait for queued metadata checkpoints; primarily used by shutdown/tests."""
        with self._metadata_persistence_guard:
            idle = self._metadata_persistence_idle.get(session.stream_id)
        return True if idle is None else idle.wait(timeout)

    def _drain_session_persistence(self) -> None:
        while True:
            with self._metadata_persistence_guard:
                if not self._metadata_persistence_pending:
                    self._metadata_persistence_worker_running = False
                    return
                stream_id = next(iter(self._metadata_persistence_pending))
                session = self._metadata_persistence_pending.pop(stream_id)
            try:
                self._persist_session(session)
            except Exception:
                _LOGGER.exception("Failed to persist SHSD session metadata for %s", stream_id)
            finally:
                with self._metadata_persistence_guard:
                    if stream_id not in self._metadata_persistence_pending:
                        self._metadata_persistence_idle.setdefault(stream_id, Event()).set()

    def _restore_sessions(self) -> None:
        """Restore local event journals without starting another media analysis."""
        if not self.data_dir.is_dir():
            return
        valid_levels = {"L0", "L1", "L2", "L3"}
        valid_statuses = {"queued", "running", "stopping", "stopped", "completed", "failed"}
        for database_path in sorted(self.data_dir.glob("*.sqlite3")):
            stream_id = database_path.stem
            if not _STREAM_ID.fullmatch(stream_id):
                continue
            try:
                with EventStore(database_path) as store:
                    metadata = store.load_stream_metadata(stream_id)
                    epoch = _metadata_int(metadata, "epoch", 0) if metadata else 0
                    events = store.current_events(stream_id, epoch)
            except (OSError, sqlite3.Error, ValueError):
                continue
            if metadata is None:
                continue
            source_value = metadata.get("source")
            if not isinstance(source_value, str) or not source_value:
                continue
            levels_value = metadata.get("levels")
            levels = (
                tuple(
                    cast(StreamLevel, level)
                    for level in levels_value
                    if isinstance(level, str) and level in valid_levels
                )
                if isinstance(levels_value, list)
                else ()
            )
            if not levels:
                levels = ("L0", "L1")
            raw_status = metadata.get("status")
            status: StreamStatus = (
                cast(StreamStatus, raw_status)
                if isinstance(raw_status, str) and raw_status in valid_statuses
                else "failed"
            )
            error_value = metadata.get("error")
            error = error_value if isinstance(error_value, str) else None
            restore_changed = metadata.get("status") != status or metadata.get("error") != error
            if status in {"queued", "running", "stopping"}:
                status = "failed"
                error = "stream interrupted by server restart; saved events remain available"
                restore_changed = True

            created_at = metadata.get("created_at_utc")
            source_duration = _metadata_int(metadata, "source_duration_ms", -1)
            raw_overflow_policy = metadata.get("prefetch_overflow_policy")
            overflow_policy: OverflowPolicy = (
                raw_overflow_policy
                if raw_overflow_policy in {"block", "drop_newest", "drop_oldest"}
                else "drop_oldest"
                if _is_live_source(source_value)
                else "block"
            )
            prefetch_capacity = _metadata_int(metadata, "prefetch_capacity", 0)
            session = StreamSession(
                stream_id=stream_id,
                source=_restore_source(source_value),
                database_path=database_path,
                levels=levels,
                threads=_metadata_int(metadata, "threads", 4),
                window_ms=_metadata_int(metadata, "window_ms", 5_000),
                minimum_similarity=_metadata_float(metadata, "minimum_similarity", 0.60),
                minimum_margin=_metadata_float(metadata, "minimum_margin", 0.05),
                top_k=_metadata_int(metadata, "top_k", 3),
                created_at_utc=created_at if isinstance(created_at, str) else "",
                speech_enabled=metadata.get("speech_enabled") is True,
                sampling_profile=(
                    cast(Literal["standard", "adaptive"], metadata["sampling_profile"])
                    if metadata.get("sampling_profile") in {"standard", "adaptive"}
                    else "standard"
                ),
                vision_profile=(
                    cast(Literal["standard", "compact"], metadata["vision_profile"])
                    if metadata.get("vision_profile") in {"standard", "compact"}
                    else "standard"
                ),
                prefetch_overflow_policy=overflow_policy,
                prefetch_capacity=prefetch_capacity if prefetch_capacity > 0 else None,
                status=status,
                epoch=_metadata_int(metadata, "epoch", 0),
                source_duration_ms=source_duration if source_duration >= 0 else None,
                modalities=_metadata_dict(metadata, "modalities"),
                watermarks=_metadata_dict(metadata, "watermarks"),
                metrics=_metadata_dict(metadata, "metrics"),
                error=error,
                journal=deque(maxlen=self.journal_limit),
            )
            session.event_heads = {event.event_id: event.revision for event in events}
            jobs = metadata.get("refine_jobs")
            if isinstance(jobs, list):
                for job in jobs:
                    if not isinstance(job, dict) or not isinstance(job.get("job_id"), str):
                        continue
                    if job.get("status") in {"queued", "running"}:
                        job["status"] = "failed"
                        job["error"] = "refine interrupted by server restart"
                        restore_changed = True
                    session.refine_jobs[job["job_id"]] = job
            self._streams[stream_id] = session
            if restore_changed:
                self._persist_session(session)

    def create_stream(
        self,
        *,
        source: str | Path,
        stream_id: str | None,
        levels: tuple[StreamLevel, ...],
        threads: int,
        window_ms: int,
        minimum_similarity: float,
        minimum_margin: float,
        top_k: int,
        speech_enabled: bool = False,
        sampling_profile: Literal["standard", "adaptive"] = "standard",
        vision_profile: Literal["standard", "compact"] = "standard",
        prefetch_overflow_policy: OverflowPolicy = "block",
        prefetch_capacity: int | None = None,
    ) -> StreamSession:
        chosen_id = stream_id or uuid.uuid4().hex
        if not _STREAM_ID.fullmatch(chosen_id):
            raise ValueError(
                "stream_id must contain 1–64 letters, digits, dots, dashes, or underscores"
            )
        if prefetch_overflow_policy not in {"block", "drop_newest", "drop_oldest"}:
            raise ValueError("unsupported prefetch overflow policy")
        if sampling_profile not in {"standard", "adaptive"}:
            raise ValueError("sampling profile must be standard or adaptive")
        if vision_profile not in {"standard", "compact"}:
            raise ValueError("vision profile must be standard or compact")
        if prefetch_capacity is not None and prefetch_capacity < 1:
            raise ValueError("prefetch_capacity must be positive")
        if _is_live_source(source) and prefetch_overflow_policy == "block":
            raise ValueError("live RTSP sources require a non-blocking overflow policy")
        if chosen_id in self._streams:
            raise KeyError(f"stream already exists: {chosen_id}")
        database_path = self.data_dir / f"{chosen_id}.sqlite3"
        if database_path.exists():
            raise KeyError(f"stream ID already has persisted data: {chosen_id}")
        session = StreamSession(
            stream_id=chosen_id,
            source=(
                source
                if isinstance(source, str) and "://" in source
                else Path(source).expanduser().resolve()
            ),
            database_path=database_path,
            levels=levels,
            threads=threads,
            window_ms=window_ms,
            minimum_similarity=minimum_similarity,
            minimum_margin=minimum_margin,
            top_k=top_k,
            created_at_utc=datetime.now(UTC).isoformat(),
            speech_enabled=speech_enabled,
            sampling_profile=sampling_profile,
            vision_profile=vision_profile,
            prefetch_overflow_policy=prefetch_overflow_policy,
            prefetch_capacity=prefetch_capacity,
            journal=deque(maxlen=self.journal_limit),
        )
        self._streams[chosen_id] = session
        self._persist_session(session)
        self._append_message(session, "stream.created", {"status": session.status})
        self.load_controller.register_source(chosen_id)
        task = asyncio.create_task(self._run_analysis(session))
        self._analysis_tasks.add(task)
        task.add_done_callback(self._analysis_tasks.discard)
        return session

    async def shutdown(self) -> None:
        """Stop active sessions, drain background work, and close pooled dispatchers."""
        for session in self._streams.values():
            if session.status in {"queued", "running", "stopping"}:
                session.stop_event.set()
        tasks = tuple(self._analysis_tasks)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._refine_dispatch_task is not None:
            await self._refine_queue.join()
            await self._refine_dispatch_task
        persistence_drained = await asyncio.gather(
            *(
                asyncio.to_thread(self._wait_for_session_persistence, session, 30)
                for session in self._streams.values()
            )
        )
        if not all(persistence_drained):
            raise TimeoutError("SHSD session metadata did not drain before shutdown")
        await asyncio.to_thread(self.embedding_provider_pool.close_dispatchers, timeout=30)

    def get(self, stream_id: str) -> StreamSession | None:
        return self._streams.get(stream_id)

    def stop_stream(self, session: StreamSession) -> None:
        """Request cooperative shutdown of a queued or running analysis."""
        if session.status in {"completed", "failed", "stopped"}:
            raise RuntimeError(f"stream is already {session.status}")
        if session.status != "stopping":
            session.stop_event.set()
            session.status = "stopping"
            self._schedule_session_persist(session)
            self._append_message(session, "stream.stopping", {"status": session.status})

    def sessions(self) -> tuple[StreamSession, ...]:
        """Return an immutable snapshot of known stream sessions."""
        return tuple(self._streams.values())

    @property
    def refine_queue_depth(self) -> int:
        """Queued refine work excludes the currently running interval."""
        return self._refine_queue.qsize()

    def stream_payload(self, session: StreamSession) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "stream_id": session.stream_id,
            "epoch": session.epoch,
            "source": _source_label(session.source),
            "status": session.status,
            "health": "error" if session.status == "failed" else session.status,
            "profile": "default",
            "levels": list(session.levels),
            "speech_enabled": session.speech_enabled,
            "sampling_profile": session.sampling_profile,
            "vision_profile": session.vision_profile,
            "prefetch_overflow_policy": session.prefetch_overflow_policy,
            "prefetch_capacity": session.prefetch_capacity,
            "modalities": session.modalities,
            "source_duration_ms": session.source_duration_ms,
            "created_at_utc": session.created_at_utc,
            "last_sequence": session.sequence,
            "error": session.error,
            "refine_jobs": list(session.refine_jobs.values()),
        }

    def timeline(
        self,
        session: StreamSession,
        *,
        from_ms: int | None,
        to_ms: int | None,
        level: str | None,
        include_history: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        with EventStore(session.database_path) as store:
            events = (
                store.all_revisions(session.stream_id, session.epoch)
                if include_history
                else store.current_events(session.stream_id, session.epoch)
            )
        filtered = [
            event
            for event in events
            if (from_ms is None or event.end_ms > from_ms)
            and (to_ms is None or event.start_ms < to_ms)
            and (level is None or event.level == level)
        ]
        filtered.sort(key=lambda item: (item.start_ms, item.end_ms, item.event_id, item.revision))
        return [event.to_dict() for event in filtered[:limit]]

    def event_detail(self, session: StreamSession, event_id: str) -> list[dict[str, Any]]:
        with EventStore(session.database_path) as store:
            revisions = store.history(session.stream_id, session.epoch, event_id)
        return [event.to_dict() for event in revisions]

    def captions(self, session: StreamSession) -> list[dict[str, Any]]:
        with EventStore(session.database_path) as store:
            return list(store.captions(session.stream_id, session.epoch))

    def speech_segments(
        self,
        session: StreamSession,
        *,
        from_ms: int | None = None,
        to_ms: int | None = None,
        limit: int = 1_000,
    ) -> list[dict[str, Any]]:
        with EventStore(session.database_path) as store:
            return list(
                store.speech_segments(
                    session.stream_id,
                    session.epoch,
                    from_ms=from_ms,
                    to_ms=to_ms,
                    limit=limit,
                )
            )

    def subscribe(
        self, session: StreamSession, after_seq: int
    ) -> tuple[asyncio.Queue[dict[str, Any]], list[dict[str, Any]]]:
        if after_seq < 0 or after_seq > session.sequence:
            raise ValueError(f"after_seq must be between 0 and {session.sequence}")
        oldest = session.journal[0]["sequence"] if session.journal else session.sequence + 1
        backlog: list[dict[str, Any]] = []
        if after_seq < oldest - 1:
            backlog.append(
                {
                    "schema_version": 1,
                    "stream_id": session.stream_id,
                    "epoch": session.epoch,
                    "sequence": oldest - 1,
                    "type": "stream.gap_detected",
                    "created_at_utc": datetime.now(UTC).isoformat(),
                    "data": {
                        "reason": "backfill_window_expired",
                        "from_seq": after_seq + 1,
                        "to_seq": oldest - 1,
                        "backfill_url": f"/v1/streams/{session.stream_id}/timeline",
                    },
                }
            )
        backlog.extend(message for message in session.journal if message["sequence"] > after_seq)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self.subscriber_queue_size)
        session.subscribers.add(queue)
        return queue, backlog

    @staticmethod
    def unsubscribe(session: StreamSession, queue: asyncio.Queue[dict[str, Any]]) -> None:
        session.subscribers.discard(queue)

    def start_refine(
        self,
        session: StreamSession,
        *,
        start_ms: int,
        end_ms: int,
        level: RefineLevel,
    ) -> dict[str, Any]:
        if session.status != "completed":
            raise RuntimeError("refine is available after the file analysis has completed")
        if end_ms > (session.source_duration_ms or 0):
            raise ValueError("refine interval must be within the known media duration")
        job_id = uuid.uuid4().hex
        job = {
            "job_id": job_id,
            "level": level,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "status": "queued",
        }
        work = next(
            (
                pending
                for pending in self._refine_pending
                if level == "L3"
                and pending.session is session
                and pending.level == "L3"
                and start_ms <= pending.end_ms + self.refine_merge_window_ms
                and end_ms + self.refine_merge_window_ms >= pending.start_ms
            ),
            None,
        )
        if work is None:
            if self._refine_queue.full():
                raise RefineQueueFullError(
                    "refine queue is full; retry after queued work completes"
                )
            self._refine_sequence += 1
            work = RefineWork(
                session=session,
                level=level,
                start_ms=start_ms,
                end_ms=end_ms,
                job_ids=[job_id],
                sequence=self._refine_sequence,
            )
            priority = 3 if level == "L2" else 4
            self._refine_queue.put_nowait((priority, work.sequence, work))
            self._refine_pending.append(work)
        else:
            work.start_ms = min(work.start_ms, start_ms)
            work.end_ms = max(work.end_ms, end_ms)
            work.job_ids.append(job_id)
            job["coalesced_into"] = work.job_ids[0]
        session.refine_jobs[job_id] = job
        self._append_message(session, "stream.refine.queued", dict(job))
        self._schedule_session_persist(session)
        if self._refine_dispatch_task is None or self._refine_dispatch_task.done():
            self._refine_dispatch_task = asyncio.create_task(self._drain_refine_queue())
        return job

    def _append_message(
        self, session: StreamSession, message_type: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        if message_type not in MESSAGE_TYPES:
            raise ValueError(f"unsupported stream message type: {message_type}")
        session.sequence += 1
        message = {
            "schema_version": 1,
            "stream_id": session.stream_id,
            "epoch": session.epoch,
            "sequence": session.sequence,
            "type": message_type,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "data": data,
        }
        session.journal.append(message)
        for queue in tuple(session.subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                overflow_notice = dict(message)
                overflow_notice["type"] = "stream.gap_detected"
                overflow_notice["data"] = {
                    "reason": "subscriber_backpressure",
                    "backfill_after_seq": max(0, session.sequence - 1),
                }
                queue.put_nowait(overflow_notice)
        return message

    def _handle_analysis_record(self, session: StreamSession, record: dict[str, Any]) -> None:
        record_type = record.get("record_type")
        record_epoch = record.get("epoch")
        if record_type == "watermark":
            snapshot = record.get("watermarks")
            record_epoch = snapshot.get("epoch") if isinstance(snapshot, dict) else None
        if isinstance(record_epoch, int) and not isinstance(record_epoch, bool):
            if record_epoch < session.epoch:
                return
            if record_epoch > session.epoch:
                session.epoch = record_epoch
                session.watermarks = None
                session.metrics = None
                session.event_heads.clear()
                session.gap_signatures.clear()
                self._schedule_session_persist(session)
        if record_type == "analysis":
            session.modalities = record.get("modalities")
            duration = record.get("source_duration_ms")
            session.source_duration_ms = duration if isinstance(duration, int) else None
            self._schedule_session_persist(session)
            return
        if record_type == "watermark":
            session.watermarks = record
            self._schedule_session_persist(session)
            self._append_message(session, "stream.watermarks.changed", record)
            watermarks = record.get("watermarks", {})
            issues = watermarks.get("issues", []) if isinstance(watermarks, dict) else []
            for issue in issues:
                if not isinstance(issue, dict) or issue.get("status") not in {
                    "gap",
                    "dropped",
                    "failed",
                }:
                    continue
                signature = (
                    issue.get("stage"),
                    issue.get("modality"),
                    issue.get("level"),
                    issue.get("start_ms"),
                    issue.get("end_ms"),
                    issue.get("status"),
                )
                if signature not in session.gap_signatures:
                    session.gap_signatures.add(signature)
                    self._append_message(session, "stream.gap_detected", issue)
            return
        if record_type == "event":
            event_id = record.get("event_id")
            revision = record.get("revision")
            if not isinstance(event_id, str) or not isinstance(revision, int):
                self._append_message(
                    session, "stream.error", {"code": "invalid_event", "record": record}
                )
                return
            current_revision = session.event_heads.get(event_id, 0)
            if revision <= current_revision:
                return
            if revision != current_revision + 1:
                self._append_message(
                    session,
                    "stream.error",
                    {
                        "code": "revision_gap",
                        "event_id": event_id,
                        "expected_revision": current_revision + 1,
                        "received_revision": revision,
                    },
                )
                return
            session.event_heads[event_id] = revision
            state = record.get("state")
            if revision == 1:
                message_type = "stream.event.created"
            elif state == "committed":
                message_type = "stream.event.committed"
            else:
                message_type = "stream.event.revised"
            self._append_message(session, message_type, record)
            return
        if record_type == "caption":
            with EventStore(session.database_path) as store:
                store.append_caption(session.stream_id, session.epoch, record)
            self._append_message(session, "stream.caption.ready", record)
            return
        if record_type == "speech_segment":
            message_type = (
                "stream.speech.segment.revised"
                if record.get("revision", 1) != 1
                else "stream.speech.segment"
            )
            self._append_message(session, message_type, record)
            return
        if record_type in {"narration_error", "error"}:
            self._append_message(session, "stream.error", record)
            return
        if record_type == "metrics":
            session.metrics = record

    async def _run_analysis(self, session: StreamSession) -> None:
        if session.stop_event.is_set():
            self.load_controller.forget(session.stream_id)
            session.status = "stopped"
            await asyncio.to_thread(self._persist_session, session)
            self._append_message(session, "stream.stopped", {"status": session.status})
            return
        session.status = "running"
        await asyncio.to_thread(self._persist_session, session)
        self._append_message(session, "stream.started", {"status": session.status})
        loop = asyncio.get_running_loop()
        watermark_lock = Lock()
        pending_watermark: dict[str, Any] | None = None
        watermark_dispatch_scheduled = False
        watermark_records_coalesced = 0
        reconnect_attempts = 0
        analysis_started = False
        current_attempt_epoch = session.epoch

        def publish_latest_watermark() -> None:
            nonlocal pending_watermark, watermark_dispatch_scheduled
            with watermark_lock:
                record = pending_watermark
                pending_watermark = None
                watermark_dispatch_scheduled = False
            if record is not None:
                self._handle_analysis_record(session, record)

        def emit(record: dict[str, Any]) -> None:
            nonlocal analysis_started
            nonlocal pending_watermark, watermark_dispatch_scheduled
            nonlocal watermark_records_coalesced
            if record.get("record_type") == "analysis":
                analysis_started = True
            if "epoch" not in record and record.get("record_type") != "watermark":
                record = {**record, "epoch": current_attempt_epoch}
            if record.get("record_type") != "watermark":
                loop.call_soon_threadsafe(self._handle_analysis_record, session, record)
                return
            with watermark_lock:
                if pending_watermark is not None:
                    watermark_records_coalesced += 1
                pending_watermark = record
                if watermark_dispatch_scheduled:
                    return
                watermark_dispatch_scheduled = True
            loop.call_soon_threadsafe(publish_latest_watermark)

        result: dict[str, Any] = {}
        try:
            while True:
                current_attempt_epoch = session.epoch
                analysis_started = False
                try:
                    result = await asyncio.to_thread(
                        self.analysis_runner,
                        session.source,
                        self.models_lock["models"]["embeddinggemma2"],
                        self.models_dir,
                        stream_id=session.stream_id,
                        epoch=current_attempt_epoch,
                        threads=session.threads,
                        window_ms=session.window_ms,
                        policy=MatchPolicy(
                            minimum_similarity=session.minimum_similarity,
                            minimum_margin=session.minimum_margin,
                            top_k=session.top_k,
                        ),
                        levels=frozenset(session.levels),
                        cache_dir=self.cache_dir,
                        event_database=session.database_path,
                        emit=emit,
                        speech_enabled=session.speech_enabled,
                        prefetch_overflow_policy=session.prefetch_overflow_policy,
                        sampling_profile=session.sampling_profile,
                        vision_profile=session.vision_profile,
                        prefetch_capacity=session.prefetch_capacity,
                        stop_event=session.stop_event,
                        runtime_load_controller=self.load_controller,
                        load_source_id=session.stream_id,
                        embedding_provider_pool=self.embedding_provider_pool,
                    )
                    break
                except LiveSourceInterruptedError:
                    if session.stop_event.is_set():
                        session.status = "stopped"
                        session.error = None
                        await asyncio.to_thread(self._persist_session, session)
                        self._append_message(session, "stream.stopped", {"status": session.status})
                        return
                    if (
                        not _is_live_source(session.source)
                        or reconnect_attempts >= _LIVE_RECONNECT_MAX_ATTEMPTS
                    ):
                        raise

                    reconnect_attempts += 1
                    retry_delay = min(
                        _LIVE_RECONNECT_MAX_DELAY_SECONDS,
                        _LIVE_RECONNECT_INITIAL_DELAY_SECONDS * (2 ** (reconnect_attempts - 1)),
                    )
                    if analysis_started:
                        session.epoch = current_attempt_epoch + 1
                        session.watermarks = None
                        session.metrics = None
                        session.event_heads.clear()
                        session.gap_signatures.clear()
                    session.error = None
                    self._schedule_session_persist(session)
                    self._append_message(
                        session,
                        "stream.reconnecting",
                        {
                            "status": session.status,
                            "epoch": session.epoch,
                            "attempt": reconnect_attempts,
                            "max_attempts": _LIVE_RECONNECT_MAX_ATTEMPTS,
                            "retry_in_seconds": retry_delay,
                            "reason": "source_interrupted",
                        },
                    )
                    self.load_controller.forget(session.stream_id)
                    stopped = await asyncio.to_thread(session.stop_event.wait, retry_delay)
                    if stopped:
                        session.status = "stopped"
                        await asyncio.to_thread(self._persist_session, session)
                        self._append_message(session, "stream.stopped", {"status": session.status})
                        return
        except Exception as error:
            if session.stop_event.is_set():
                session.status = "stopped"
                session.error = _safe_error(session.source, error)
                await asyncio.to_thread(self._persist_session, session)
                self._append_message(session, "stream.stopped", {"status": session.status})
                return
            session.status = "failed"
            session.error = _safe_error(session.source, error)
            await asyncio.to_thread(self._persist_session, session)
            self._append_message(
                session, "stream.error", {"code": "analysis_failed", "message": session.error}
            )
            return
        finally:
            self.load_controller.forget(session.stream_id)
        await asyncio.sleep(0)
        session.metrics = {
            **result,
            "api_reconnect_attempts": reconnect_attempts,
            "api_watermark_records_coalesced": watermark_records_coalesced,
            "api_metadata_checkpoints_coalesced": (
                self._metadata_persistence_coalesced.get(session.stream_id, 0)
            ),
        }
        session.status = "stopped" if session.stop_event.is_set() else "completed"
        await asyncio.to_thread(self._persist_session, session)
        self._append_message(
            session,
            "stream.stopped" if session.status == "stopped" else "stream.completed",
            {"status": session.status, "metrics": session.metrics},
        )

    async def _drain_refine_queue(self) -> None:
        cancelled = False
        try:
            while not self._refine_queue.empty():
                _priority, _sequence, work = await self._refine_queue.get()
                if work in self._refine_pending:
                    self._refine_pending.remove(work)
                try:
                    await self._run_refine_work(work)
                finally:
                    self._refine_queue.task_done()
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            self._refine_dispatch_task = None
            if not cancelled and not self._refine_queue.empty():
                self._refine_dispatch_task = asyncio.create_task(self._drain_refine_queue())

    async def _run_refine_work(self, work: RefineWork) -> None:
        session = work.session
        jobs = [session.refine_jobs[job_id] for job_id in work.job_ids]
        for job in jobs:
            job["status"] = "running"
            if len(jobs) > 1:
                job["execution_interval_ms"] = [work.start_ms, work.end_ms]
            self._append_message(session, "stream.refine.started", dict(job))
        execution = {
            **jobs[0],
            "level": work.level,
            "start_ms": work.start_ms,
            "end_ms": work.end_ms,
        }
        loop = asyncio.get_running_loop()

        def emit(record: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(self._handle_analysis_record, session, record)

        try:
            await asyncio.to_thread(self._refine_sync, session, execution, emit)
        except Exception as error:
            await asyncio.sleep(0)
            error_message = f"{type(error).__name__}: {error}"[:500]
            for job in jobs:
                job["status"] = "failed"
                job["error"] = error_message
            try:
                tracker = self._restore_watermark_tracker(session)
                start_ms = work.start_ms
                end_ms = work.end_ms
                level = work.level
                tracker.mark(
                    "D",
                    start_ms,
                    end_ms,
                    "failed",
                    level=level,
                    revision=2,
                    reason="refine_failed",
                )
                tracker.mark(
                    "R",
                    start_ms,
                    end_ms,
                    "failed",
                    level=level,
                    revision=2,
                    reason="refine_failed",
                )
                horizon = session.source_duration_ms or end_ms
                snapshot = tracker.snapshot(through_ms=horizon)
                self._handle_analysis_record(
                    session,
                    {
                        "record_type": "watermark",
                        "schema_version": 1,
                        "source_end_ms": horizon,
                        "watermarks": snapshot.to_dict(),
                        "backlog_ms": {
                            item: max(0, horizon - snapshot.R_ms[item])
                            for item in ("L1", "L2", "L3")
                        },
                    },
                )
            except Exception as watermark_error:
                for job in jobs:
                    job["watermark_error"] = f"{type(watermark_error).__name__}: {watermark_error}"[
                        :250
                    ]
            self._append_message(
                session,
                "stream.error",
                {
                    "code": "refine_failed",
                    "job_ids": work.job_ids,
                    "message": error_message,
                },
            )
            self._schedule_session_persist(session)
        else:
            await asyncio.sleep(0)
            for job in jobs:
                job["status"] = "completed"
            self._schedule_session_persist(session)
            for job in jobs:
                self._append_message(session, "stream.refine.completed", dict(job))

    def _refine_sync(
        self,
        session: StreamSession,
        job: dict[str, Any],
        emit: Callable[[dict[str, Any]], None],
    ) -> None:
        start_ms = int(job["start_ms"])
        end_ms = int(job["end_ms"])
        level = job["level"]
        with EventStore(session.database_path) as store:
            current_events = [
                event
                for event in store.current_events(session.stream_id, session.epoch)
                if event.start_ms < end_ms and event.end_ms > start_ms
            ]
            if level == "L2":
                reducer = TemporalStateReducer(min_repeats=2)
                for event in sorted(
                    current_events, key=lambda item: (item.start_ms, item.end_ms, item.event_id)
                ):
                    if event.level not in {"L0", "L1"}:
                        continue
                    delta = reducer.ingest(event)
                    if delta is not None:
                        emit(
                            {
                                "record_type": "state_delta",
                                "level": "L2",
                                "source_event_id": event.event_id,
                                "source_revision": event.revision,
                                **delta.to_dict(),
                            }
                        )
                    refined = replace(
                        event,
                        revision=event.revision + 1,
                        level="L2",
                        state="refined" if delta is not None and delta.published else "committed",
                        supersedes_revision=event.revision,
                        updated_at_utc=datetime.now(UTC).isoformat(),
                    )
                    store.append(refined, expected_revision=event.revision)
                    emit({"record_type": "event", **refined.to_dict()})
            else:
                l2_events = [event for event in current_events if event.level == "L2"]
                requests = _narration_batches(
                    l2_events, stream_id=session.stream_id, epoch=session.epoch
                )
                if not requests:
                    emit(
                        {
                            "record_type": "narration_skipped",
                            "level": "L3",
                            "reason": "no_accepted_claims_with_display_text",
                            "time_range": {"start_ms": start_ms, "end_ms": end_ms},
                        }
                    )
                else:
                    from shsd.captions.narrator import (
                        CaptionDeduplicator,
                        NarrationRequestDeduplicator,
                        QwenNarrator,
                    )

                    narrator = QwenNarrator(
                        self.models_lock["models"]["qwen3_0_6b"],
                        self.models_dir,
                        self.root,
                        threads=session.threads,
                        max_tokens=96,
                    )
                    caption_deduplicator = CaptionDeduplicator()
                    narration_request_deduplicator = NarrationRequestDeduplicator()
                    for request in requests:
                        duplicate_record = narration_request_deduplicator.should_skip(request)
                        if duplicate_record is not None:
                            emit(duplicate_record)
                            continue
                        result = narrator.narrate(request)
                        narration_request_deduplicator.remember(
                            request, caption_ru=result.response.caption_ru
                        )
                        emit(caption_deduplicator.process(result))

        tracker = self._restore_watermark_tracker(session)
        tracker.mark("D", start_ms, end_ms, "done", level=level, revision=2)
        if level == "L2":
            tracker.mark("R", start_ms, end_ms, "done", level=level, revision=2)
        else:
            matching_caption = bool(
                requests
                and any(
                    request.time_range[0] < end_ms and request.time_range[1] > start_ms
                    for request in requests
                )
            )
            tracker.mark(
                "R",
                start_ms,
                end_ms,
                "done" if matching_caption else "skipped",
                level=level,
                revision=2,
                reason=None if matching_caption else "no_supported_claim_in_interval",
            )
        snapshot = tracker.snapshot(through_ms=session.source_duration_ms or end_ms)
        emit(
            {
                "record_type": "watermark",
                "schema_version": 1,
                "source_end_ms": session.source_duration_ms or end_ms,
                "watermarks": snapshot.to_dict(),
                "backlog_ms": {
                    item: max(0, (session.source_duration_ms or end_ms) - snapshot.R_ms[item])
                    for item in ("L1", "L2", "L3")
                },
            }
        )

    def _restore_watermark_tracker(self, session: StreamSession) -> WatermarkTracker:
        record = session.watermarks or {}
        snapshot = record.get("watermarks", {})
        modalities_data = snapshot.get("modality_cursors", {})
        modalities: set[Modality] = set(modalities_data) if modalities_data else {"audio", "video"}
        tracker = WatermarkTracker(
            session.stream_id,
            epoch=session.epoch,
            required_modalities=modalities,
        )
        horizon = session.source_duration_ms or int(record.get("source_end_ms", 0))
        if horizon <= 0:
            return tracker
        issues = snapshot.get("issues", [])

        def restore_lane(
            stage: CoverageStage,
            cursor: int,
            *,
            modality: Modality | None = None,
            level: Level | None = None,
        ) -> None:
            relevant = [
                issue
                for issue in issues
                if issue.get("stage") == stage
                and issue.get("modality") == modality
                and issue.get("level") == level
            ]
            boundaries = {0, horizon, min(horizon, max(0, cursor))}
            for issue in relevant:
                boundaries.add(max(0, min(horizon, int(issue["start_ms"]))))
                boundaries.add(max(0, min(horizon, int(issue["end_ms"]))))
            ordered = sorted(boundaries)
            for left, right in zip(ordered, ordered[1:], strict=False):
                if left >= right:
                    continue
                issue = next(
                    (
                        item
                        for item in relevant
                        if int(item["start_ms"]) <= left and int(item["end_ms"]) >= right
                    ),
                    None,
                )
                if issue is not None:
                    status = issue["status"]
                    reason = issue.get("reason")
                elif right <= cursor:
                    status = "done"
                    reason = None
                else:
                    status = "pending"
                    reason = "not_processed"
                tracker.mark(
                    stage,
                    left,
                    right,
                    status,
                    modality=modality,
                    level=level,
                    reason=reason,
                )

        modality_stages: tuple[CoverageStage, ...] = ("C", "E")
        level_stages: tuple[CoverageStage, ...] = ("D", "R")
        for modality in modalities:
            cursors = modalities_data.get(modality, {})
            for stage in modality_stages:
                restore_lane(
                    stage,
                    int(cursors.get(stage, 0)),
                    modality=modality,
                )
        for level in ("L1", "L2", "L3"):
            for stage in level_stages:
                cursors = snapshot.get(stage, {})
                restore_lane(stage, int(cursors.get(level, 0)), level=level)
        return tracker
