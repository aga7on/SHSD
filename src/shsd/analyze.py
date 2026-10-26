"""Run a bounded local CPU analysis pass and publish evidence-bearing JSONL."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections import deque
from collections.abc import Callable, Generator, Iterable, Iterator
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from fractions import Fraction
from functools import partial as bind
from functools import wraps
from pathlib import Path
from threading import Event, Lock, RLock, Thread
from typing import Any, Literal, ParamSpec, TypeVar, cast
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import av
import numpy as np

from shsd.captions.hypothesis_proposer import QwenHypothesisProposer
from shsd.detectors import analyze_audio, analyze_video_frames, compare_audio_windows
from shsd.detectors.audio import AUDIO_METHOD_VERSION
from shsd.detectors.types import SignalObservation
from shsd.embeddings.provider import (
    COMPACT_IMAGE_SOFT_TOKENS,
    DEFAULT_IMAGE_SOFT_TOKENS,
    EmbeddingProvider,
    EmbeddingProviderPool,
    EmbeddingRecord,
)
from shsd.ingest.clock import pts_to_ms
from shsd.ingest.decoder import (
    CaptureSpan,
    DecodedFrame,
    RingDecodeTelemetry,
    iter_decoded_frames_from_ring,
    iter_decoded_media_from_ring,
)
from shsd.ingest.demux import Modality, inspect_media
from shsd.ingest.prefetch import (
    MediaAdmissionTelemetry,
    OverflowPolicy,
    PrefetchTelemetry,
    iter_bounded_prefetch,
    iter_merge_by_key,
)
from shsd.memory import (
    EventStore,
    TemporalEventReducer,
    TemporalStateReducer,
    TimelineClaim,
    TimelineEvent,
    WatermarkTracker,
    WindowMatch,
)
from shsd.memory.watermarks import (
    CoverageStage,
    CoverageStatus,
    Level,
)
from shsd.memory.watermarks import (
    Modality as CoverageModality,
)
from shsd.sampling import AdaptiveSamplingController, EmbeddingNovelty, SamplingProfile
from shsd.semantic.hypotheses import (
    HypothesisAxis,
    encode_profile_candidates,
    load_profiles,
)
from shsd.semantic.iterative import IterativeHypothesisRefiner
from shsd.semantic.matcher import MatchPolicy, SemanticMatcher
from shsd.semantic.relations import CrossModalRelationValidator
from shsd.workers.asr_worker import (
    ASR_WINDOW_MS,
    BoundedSpeechWorker,
    GigaAMTranscriber,
    SpeechResult,
    SpeechTask,
    SpeechWindowAssembler,
)
from shsd.workers.embedding_worker import (
    BoundedEmbeddingWorker,
    EmbeddingJob,
    EmbeddingResult,
    SharedEmbeddingDispatcher,
)
from shsd.workers.l1_worker import BoundedL1Worker, L1Work
from shsd.workers.live_levels import LiveLevelWorkers
from shsd.workers.scheduler import (
    AsyncLevelScheduler,
    JobKey,
    LoadMode,
    LoadSample,
    RuntimeLoadController,
    ScheduledJob,
    SubmitResult,
    WorkPriority,
)

SAMPLE_RATE = 16_000
VIDEO_SIGNAL_PERIOD_MS = 1_000
AUDIO_PREFETCH_CAPACITY = 64
VIDEO_PREFETCH_CAPACITY = 8
_RESOURCE_SAMPLE_INTERVAL_S = 0.05
_P = ParamSpec("_P")
_R = TypeVar("_R")


class ProcessRssSampler:
    """Sample host CPU and process-tree RSS across the complete media pass."""

    def __init__(self, interval_s: float = _RESOURCE_SAMPLE_INTERVAL_S) -> None:
        self.interval_s = interval_s
        self._process: Any = None
        self._peak_rss_bytes = 0
        self._peak_process_count = 0
        self._current_rss_bytes = 0
        self._system_cpu_percent = 0.0
        self._sample_lock = Lock()
        self._available = False
        self._stop = Event()
        self._thread = Thread(target=self._sample_loop, name="shsd-rss-sampler", daemon=True)

    def start(self) -> None:
        try:
            import psutil

            self._process = psutil.Process()
            self._available = True
        except Exception:
            return
        self._sample_once()
        self._thread.start()

    def stop(self) -> None:
        if not self._available:
            return
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._sample_once()

    def snapshot(self) -> dict[str, int | float | bool]:
        with self._sample_lock:
            current_rss_bytes = self._current_rss_bytes
            peak_rss_bytes = self._peak_rss_bytes
            peak_process_count = self._peak_process_count
            system_cpu_percent = self._system_cpu_percent
        return {
            "available": self._available,
            "current_process_tree_rss_bytes": current_rss_bytes,
            "peak_process_tree_rss_bytes": peak_rss_bytes,
            "peak_process_count": peak_process_count,
            "system_cpu_percent": round(system_cpu_percent, 2),
            "sample_interval_ms": round(self.interval_s * 1000),
        }

    @property
    def available(self) -> bool:
        return self._available

    def load_sample(
        self,
        *,
        queue_depth: int,
        queue_capacity: int,
        source_lag_ms: int,
        memory_limit_bytes: int,
    ) -> LoadSample:
        """Combine the latest nonblocking host sample with live queue pressure."""
        with self._sample_lock:
            cpu_percent = self._system_cpu_percent
            rss_bytes = self._current_rss_bytes
        return LoadSample(
            queue_depth=queue_depth,
            queue_capacity=queue_capacity,
            source_lag_ms=source_lag_ms,
            cpu_percent=cpu_percent,
            rss_bytes=rss_bytes,
            memory_limit_bytes=memory_limit_bytes,
        )

    def _sample_loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            self._sample_once()

    def _sample_once(self) -> None:
        if self._process is None:
            return
        try:
            import psutil

            system_cpu_percent = min(
                100.0,
                max(0.0, float(psutil.cpu_percent(interval=None))),
            )
            processes = [self._process, *self._process.children(recursive=True)]
            rss_bytes = 0
            live_process_count = 0
            for process in processes:
                try:
                    rss_bytes += int(process.memory_info().rss)
                    live_process_count += 1
                except Exception:
                    continue
            with self._sample_lock:
                self._current_rss_bytes = rss_bytes
                self._system_cpu_percent = system_cpu_percent
                self._peak_rss_bytes = max(self._peak_rss_bytes, rss_bytes)
                self._peak_process_count = max(
                    self._peak_process_count,
                    live_process_count,
                )
        except Exception:
            self._available = False
            self._process = None


_ACTIVE_RESOURCE_SAMPLER: ContextVar[ProcessRssSampler | None] = ContextVar(
    "shsd_active_resource_sampler", default=None
)


def _sample_process_rss(function: Callable[_P, _R]) -> Callable[_P, _R]:
    """Keep a whole-call RSS high-water mark available to the emitted metrics row."""

    @wraps(function)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        sampler = ProcessRssSampler()
        sampler.start()
        token = _ACTIVE_RESOURCE_SAMPLER.set(sampler)
        try:
            return function(*args, **kwargs)
        finally:
            sampler.stop()
            _ACTIVE_RESOURCE_SAMPLER.reset(token)

    return wrapped


def _host_load_sample() -> tuple[LoadSample, bool]:
    """Measure host CPU/RSS for file-analysis admission when psutil is present."""
    try:
        memory_limit_bytes = max(0, int(os.environ.get("SHSD_MEMORY_LIMIT_BYTES", "0")))
    except ValueError:
        memory_limit_bytes = 0
    try:
        import psutil

        sample = LoadSample(
            queue_depth=0,
            queue_capacity=64,
            cpu_percent=min(100.0, max(0.0, float(psutil.cpu_percent(interval=0.1)))),
            rss_bytes=int(psutil.Process().memory_info().rss),
            memory_limit_bytes=memory_limit_bytes,
        )
    except Exception:
        sample = LoadSample(
            queue_depth=0,
            queue_capacity=64,
            memory_limit_bytes=memory_limit_bytes,
        )
        return sample, False
    return sample, True


def _source_label(source: str | Path) -> str:
    """Return a stable source label without URL credentials or query tokens."""
    if isinstance(source, Path):
        return str(source.resolve())
    if "://" not in source:
        return source
    parsed = urlsplit(source)
    hostname = parsed.hostname or ""
    if parsed.port is not None:
        hostname = f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))


def _source_duration_ms(source: str | Path) -> int | None:
    """Read the container duration in milliseconds when the source provides it."""
    if isinstance(source, str) and "://" in source:
        return None
    with av.open(str(source), mode="r") as container:
        duration = container.duration
    return max(1, round(duration / 1000)) if duration is not None and duration > 0 else None


def _fill_coverage_gaps(
    tracker: WatermarkTracker,
    stage: CoverageStage,
    end_ms: int,
    *,
    modality: Modality | Literal["speech"] | None = None,
    level: Level | None = None,
    reason: str = "not_observed",
) -> None:
    """Make decode/analysis holes explicit once the finite file pass is complete."""
    if end_ms <= 0:
        return
    spans = tracker.spans(stage, modality=modality, level=level)
    cursor = 0
    for span in spans:
        if cursor >= end_ms:
            break
        if span.start_ms > cursor:
            tracker.mark(
                stage,
                cursor,
                min(end_ms, span.start_ms),
                "gap",
                modality=modality,
                level=level,
                reason=reason,
            )
        cursor = max(cursor, span.end_ms)
    if cursor < end_ms:
        tracker.mark(
            stage,
            cursor,
            end_ms,
            "gap",
            modality=modality,
            level=level,
            reason=reason,
        )


def _mark_initial_capture_gap(
    tracker: WatermarkTracker, modality: Modality, first_start_ms: int
) -> None:
    """Close the leading C interval when a source's first packet starts after zero."""
    if first_start_ms > 0:
        tracker.mark(
            "C",
            0,
            first_start_ms,
            "gap",
            modality=modality,
            reason="not_observed_by_decoder",
        )


def _active_levels(levels: frozenset[str]) -> frozenset[str]:
    """Include prerequisite semantic levels for a requested higher-level result."""
    active = set(levels)
    if "L3" in active:
        active.add("L2")
    if "L2" in active:
        active.add("L1")
    return frozenset(active)


def _narration_batches(
    events: list[TimelineEvent],
    *,
    stream_id: str,
    epoch: int,
) -> list[Any]:
    """Build small, source-linked narrator batches from accepted event claims."""
    from shsd.captions.narrator import NarrationClaim, NarrationEventRef, NarrationRequest

    sources: list[tuple[TimelineEvent, Any]] = []
    for event in events:
        for claim in event.claims:
            if claim.decision == "accepted" and claim.text_ru:
                sources.append((event, claim))

    batches: list[Any] = []
    # Keep each model request small enough for the bounded local context. The
    # complete evidence list remains in the event record; the prompt needs only
    # a compact set of references plus the exact event revision.
    for offset in range(0, len(sources), 3):
        source_batch = sources[offset : offset + 3]
        refs_by_id: dict[str, NarrationEventRef] = {}
        claims: list[NarrationClaim] = []
        for event, claim in source_batch:
            refs_by_id[event.event_id] = NarrationEventRef(event.event_id, event.revision)
            claims.append(
                NarrationClaim(
                    claim_id=f"{event.event_id}:{claim.claim_id}",
                    event_id=event.event_id,
                    revision=event.revision,
                    start_ms=event.start_ms,
                    end_ms=event.end_ms,
                    text_ru=claim.text_ru,
                    evidence_refs=claim.evidence_refs[:12],
                )
            )
        batches.append(
            NarrationRequest(
                stream_id=stream_id,
                epoch=epoch,
                event_refs=tuple(refs_by_id.values()),
                claims=tuple(claims),
            )
        )
    return batches


def _frame_time_ms(frame: Any, fallback_ms: int) -> int:
    pts = frame.pts
    time_base = frame.time_base
    if pts is None or time_base is None:
        return fallback_ms
    rational = Fraction(int(time_base.numerator), int(time_base.denominator))
    return max(0, pts_to_ms(int(pts), rational))


@dataclass(frozen=True, slots=True)
class _SelectedVideoWork:
    frame: Any
    frame_ms: int
    signal_selected: bool
    embedding_selected: bool
    embedding_skip_reason: str | None = None
    on_embedding_drop: Callable[[], None] | None = None
    sampling_activity_score: float | None = None
    signal_frame_small: np.ndarray | None = None


def _video_signal_frame(item: _SelectedVideoWork) -> np.ndarray:
    """Reuse adaptive sampling's low-resolution frame for the L0 signal pass."""
    if item.signal_frame_small is not None:
        return item.signal_frame_small
    return cast(
        np.ndarray,
        item.frame.reformat(width=160, height=90, format="rgb24").to_ndarray(),
    )


def _selected_video_items(
    source_items: Iterable[CaptureSpan | DecodedFrame],
    *,
    window_ms: int,
    source_duration_ms: int | None,
    sampling: AdaptiveSamplingController,
    load_controller: RuntimeLoadController | None = None,
) -> Iterator[CaptureSpan | _SelectedVideoWork]:
    """Keep packet capture updates and only frames used by signals or embeddings."""
    selector = _VideoWorkSelector(
        window_ms=window_ms,
        source_duration_ms=source_duration_ms,
        sampling=sampling,
        load_controller=load_controller,
    )
    for item in source_items:
        yield from selector.push(item)


class _VideoWorkSelector:
    """Incrementally select video work from packet/decode events."""

    def __init__(
        self,
        *,
        window_ms: int,
        source_duration_ms: int | None,
        sampling: AdaptiveSamplingController,
        load_controller: RuntimeLoadController | None = None,
    ) -> None:
        self.window_ms = window_ms
        self.source_duration_ms = source_duration_ms
        self.sampling = sampling
        self.load_controller = load_controller
        self.last_frame_ms = -1
        self.next_signal_ms = 0
        self.next_embedding_ms = 0
        self.last_embedding_ms: int | None = None

    def embedding_dropped(self, frame_ms: int) -> None:
        """Release a stride reservation when its selected frame never reaches inference."""
        if self.last_embedding_ms != frame_ms:
            return
        self.last_embedding_ms = None
        self.next_embedding_ms = frame_ms + 1
        if self.sampling.profile == "adaptive":
            self.sampling.rollback_video_sample(frame_ms)

    def push(self, item: CaptureSpan | DecodedFrame) -> list[CaptureSpan | _SelectedVideoWork]:
        if isinstance(item, CaptureSpan):
            return [item]
        frame_ms = _frame_time_ms(item.frame, max(0, self.last_frame_ms + 1))
        if frame_ms <= self.last_frame_ms:
            return []
        self.last_frame_ms = frame_ms
        if self.source_duration_ms is not None and frame_ms >= self.source_duration_ms:
            return []
        signal_selected = frame_ms >= self.next_signal_ms
        if signal_selected:
            self.next_signal_ms = frame_ms + VIDEO_SIGNAL_PERIOD_MS
        standard_embedding_due = frame_ms >= self.next_embedding_ms
        load_mode = (
            self.load_controller.status.mode
            if self.load_controller is not None
            else LoadMode.NORMAL
        )
        stride_multiplier = (
            4
            if load_mode is LoadMode.CRITICAL
            else 2
            if load_mode is LoadMode.DEGRADED
            else 1
        )
        if self.load_controller is not None:
            active_sources = self.load_controller.active_source_count
            if active_sources >= 5:
                stride_multiplier = max(stride_multiplier, 4)
            elif active_sources >= 2:
                stride_multiplier = max(stride_multiplier, 2)
        minimum_stride_ms = self.window_ms * stride_multiplier
        runtime_throttled = (
            standard_embedding_due
            and (
                self.last_embedding_ms is None
                and stride_multiplier > 1
                and frame_ms < minimum_stride_ms
                or self.last_embedding_ms is not None
                and frame_ms - self.last_embedding_ms < minimum_stride_ms
            )
        )
        embedding_skip_reason: str | None = None
        sampling_activity_score: float | None = None
        signal_frame_small: np.ndarray | None = None
        if self.sampling.profile == "adaptive":
            embedding_selected = False
            if signal_selected:
                signal_frame_small = item.frame.reformat(
                    width=160, height=90, format="rgb24"
                ).to_ndarray()
                decision = self.sampling.select_video(
                    frame_ms,
                    signal_frame_small,
                    standard_due=False,
                    minimum_stride_ms=minimum_stride_ms,
                )
                embedding_selected = decision.selected
                if decision.reason == "activity":
                    sampling_activity_score = decision.activity_score
                if not embedding_selected:
                    embedding_skip_reason = (
                        "runtime_backpressure"
                        if decision.reason == "runtime_backpressure"
                        else "adaptive_sampling"
                    )
        else:
            embedding_selected = standard_embedding_due and not runtime_throttled
            if not embedding_selected:
                embedding_skip_reason = (
                    "runtime_backpressure" if runtime_throttled else "embedding_stride"
                )
            if signal_selected:
                self.sampling.record_standard_video(
                    embedding_selected,
                    runtime_backpressure=runtime_throttled,
                )
            if embedding_selected:
                self.next_embedding_ms = frame_ms + minimum_stride_ms
        if embedding_selected:
            self.last_embedding_ms = frame_ms
        if not (signal_selected or embedding_selected):
            return []
        on_embedding_drop: Callable[[], None] | None = None
        if embedding_selected:
            def rollback_selected_video() -> None:
                self.embedding_dropped(frame_ms)

            on_embedding_drop = rollback_selected_video
        return [
            _SelectedVideoWork(
                item.frame,
                frame_ms=frame_ms,
                signal_selected=signal_selected,
                embedding_selected=embedding_selected,
                embedding_skip_reason=embedding_skip_reason,
                on_embedding_drop=on_embedding_drop,
                sampling_activity_score=sampling_activity_score,
                signal_frame_small=signal_frame_small,
            )
        ]


def _timed_audio_work(
    items: Iterable[CaptureSpan | tuple[int, int, np.ndarray]],
) -> Iterator[tuple[int, str, object]]:
    last_ready_ms = 0
    try:
        for item in items:
            ready_ms = item.end_ms if isinstance(item, CaptureSpan) else item[1]
            last_ready_ms = max(last_ready_ms, ready_ms)
            yield last_ready_ms, "audio", item
    finally:
        close = getattr(items, "close", None)
        if callable(close):
            close()


def _timed_video_work(
    items: Iterable[CaptureSpan | _SelectedVideoWork],
) -> Iterator[tuple[int, str, object]]:
    last_frame_ms = -1
    last_ready_ms = 0
    try:
        for item in items:
            if isinstance(item, CaptureSpan):
                last_ready_ms = max(last_ready_ms, item.end_ms)
                yield last_ready_ms, "video", item
                continue
            frame_ms = item.frame_ms
            if frame_ms <= last_frame_ms:
                continue
            last_frame_ms = frame_ms
            last_ready_ms = max(last_ready_ms, frame_ms)
            yield last_ready_ms, "video", item
    finally:
        close = getattr(items, "close", None)
        if callable(close):
            close()


def _timed_shared_media_work(
    items: Iterable[tuple[Modality, CaptureSpan | DecodedFrame]],
    *,
    modalities: set[Modality],
    window_ms: int,
    source_duration_ms: int | None,
    sampling: AdaptiveSamplingController,
    load_controller: RuntimeLoadController | None = None,
) -> Iterator[tuple[int, str, object]]:
    """Transform one interleaved decoder into a timestamp-ordered work stream."""
    audio_builder = _AudioWindowBuilder(window_ms) if "audio" in modalities else None
    video_selector = (
        _VideoWorkSelector(
            window_ms=window_ms,
            source_duration_ms=source_duration_ms,
            sampling=sampling,
            load_controller=load_controller,
        )
        if "video" in modalities
        else None
    )
    last_ready_ms = 0

    for modality, item in items:
        if modality == "audio" and audio_builder is not None:
            transformed = audio_builder.push(item)
            for audio_work in transformed:
                ready_ms = (
                    audio_work.end_ms
                    if isinstance(audio_work, CaptureSpan)
                    else audio_work[1]
                )
                last_ready_ms = max(last_ready_ms, ready_ms)
                yield last_ready_ms, "audio", audio_work
        elif modality == "video" and video_selector is not None:
            for video_work in video_selector.push(item):
                ready_ms = (
                    video_work.end_ms
                    if isinstance(video_work, CaptureSpan)
                    else video_work.frame_ms
                )
                last_ready_ms = max(last_ready_ms, ready_ms)
                yield last_ready_ms, "video", video_work

    if audio_builder is not None:
        for work in audio_builder.finish():
            last_ready_ms = max(last_ready_ms, work[1])
            yield last_ready_ms, "audio", work


def _mark_prefetch_drop_coverage(
    tracker: WatermarkTracker,
    modality: Modality,
    item: object,
    reason: str,
    *,
    speech_available: bool = False,
) -> None:
    """Make model coverage lost to a bounded media queue visible in E."""
    if modality == "audio":
        start_ms, end_ms, _samples = cast(tuple[int, int, np.ndarray], item)
        start = max(0, start_ms)
        end = max(start + 1, end_ms)
        tracker.mark("E", start, end, "dropped", modality="audio", reason=reason, revision=2)
        if speech_available:
            tracker.mark("C", start, end, "dropped", modality="speech", reason=reason, revision=2)
            tracker.mark("E", start, end, "dropped", modality="speech", reason=reason, revision=2)
        return
    video_work = cast(_SelectedVideoWork, item)
    if video_work.embedding_selected:
        if video_work.on_embedding_drop is not None:
            video_work.on_embedding_drop()
        start = max(0, video_work.frame_ms)
        tracker.mark("E", start, start + 1, "dropped", modality="video", reason=reason, revision=2)


def _audio_windows(
    source_items: Iterable[CaptureSpan | DecodedFrame], window_ms: int
) -> Iterator[CaptureSpan | tuple[int, int, np.ndarray]]:
    """Resample audio and forward capture updates without crossing a gap."""
    builder = _AudioWindowBuilder(window_ms)
    for item in source_items:
        yield from builder.push(item)
    yield from builder.finish()


class _AudioWindowBuilder:
    """Incrementally resample decoded audio into fixed windows."""

    def __init__(self, window_ms: int) -> None:
        self.target_samples = max(1, round(window_ms * SAMPLE_RATE / 1000))
        self.min_partial_samples = max(1, round(SAMPLE_RATE * 0.25))
        self.resampler = av.AudioResampler(format="fltp", layout="mono", rate=SAMPLE_RATE)
        self.parts: list[np.ndarray] = []
        self.buffered = 0
        self.window_start_ms: int | None = None
        self.cursor_ms = 0

    def push(
        self, item: CaptureSpan | DecodedFrame
    ) -> list[CaptureSpan | tuple[int, int, np.ndarray]]:
        if isinstance(item, CaptureSpan):
            return [item]
        ready: list[CaptureSpan | tuple[int, int, np.ndarray]] = []
        for frame in self.resampler.resample(item.frame):
            ready.extend(self._consume(frame))
        return ready

    def _consume(self, frame: Any) -> list[tuple[int, int, np.ndarray]]:
        ready: list[tuple[int, int, np.ndarray]] = []
        samples = np.asarray(frame.to_ndarray(), dtype=np.float32).reshape(-1)
        frame_start_ms = _frame_time_ms(frame, self.cursor_ms)
        if self.window_start_ms is not None and frame_start_ms > self.cursor_ms + 3:
            if self.buffered >= self.min_partial_samples:
                ready.append(
                    (
                        self.window_start_ms,
                        max(self.window_start_ms + 1, self.cursor_ms),
                        np.concatenate(self.parts),
                    )
                )
            self.parts = []
            self.buffered = 0
            self.window_start_ms = None
            self.cursor_ms = frame_start_ms
        elif self.window_start_ms is not None and frame_start_ms < self.cursor_ms - 3:
            overlap_samples = min(
                samples.size,
                round((self.cursor_ms - frame_start_ms) * SAMPLE_RATE / 1000),
            )
            samples = samples[overlap_samples:]
            if not samples.size:
                return ready
            frame_start_ms = self.cursor_ms
        if self.window_start_ms is None:
            self.window_start_ms = frame_start_ms
            self.cursor_ms = frame_start_ms

        sample_offset = 0
        while sample_offset < samples.size:
            capacity = self.target_samples - self.buffered
            take = min(capacity, samples.size - sample_offset)
            self.parts.append(samples[sample_offset : sample_offset + take])
            sample_offset += take
            self.buffered += take
            self.cursor_ms = self.window_start_ms + round(self.buffered * 1000 / SAMPLE_RATE)
            if self.buffered == self.target_samples:
                end_ms = max(self.window_start_ms + 1, self.cursor_ms)
                ready.append((self.window_start_ms, end_ms, np.concatenate(self.parts)))
                self.window_start_ms = end_ms
                self.parts = []
                self.buffered = 0
        return ready

    def finish(self) -> list[tuple[int, int, np.ndarray]]:
        ready: list[tuple[int, int, np.ndarray]] = []
        for frame in self.resampler.resample(None):
            ready.extend(self._consume(frame))
        if (
            self.buffered >= self.min_partial_samples
            and self.window_start_ms is not None
        ):
            duration_ms = round(self.buffered * 1000 / SAMPLE_RATE)
            end_ms = max(self.window_start_ms + 1, self.window_start_ms + duration_ms)
            ready.append((self.window_start_ms, end_ms, np.concatenate(self.parts)))
        self.parts = []
        self.buffered = 0
        self.window_start_ms = None
        return ready


def _record_embedding(
    record: EmbeddingRecord,
    *,
    start_ms: int,
    end_ms: int,
    source: str | Path,
) -> dict[str, Any]:
    return {
        "record_type": "embedding",
        "level": "L0",
        "source": _source_label(source),
        "modality": record.modality,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "embedding_dim": record.embedding_dim,
        "norm": record.norm,
        "model_revision": record.model_revision,
        "preprocess_version": record.input_preprocess_version,
        "latency_ms": record.latency_ms,
        "cache_hit": record.cache_hit,
        "window_id": record.window_id,
    }


def _audio_summary(
    observations: list[SignalObservation], start_ms: int, end_ms: int
) -> dict[str, Any]:
    rms = [float(item.value) for item in observations if item.subtype == "rms"]
    loudness = [float(item.value) for item in observations if item.subtype == "loudness_dbfs"]
    active = [bool(item.value) for item in observations if item.subtype == "energy_vad"]
    onsets = [item for item in observations if item.subtype == "onset"]
    centroids = [float(item.value) for item in observations if item.subtype == "spectral_centroid"]
    return {
        "record_type": "observation",
        "level": "L0",
        "modality": "audio",
        "start_ms": start_ms,
        "end_ms": end_ms,
        "subtype": "audio_window_summary",
        "method_version": AUDIO_METHOD_VERSION,
        "quality": round(float(np.mean([item.quality for item in observations])), 4),
        "value": {
            "mean_rms_full_scale": round(float(np.mean(rms)), 6) if rms else 0.0,
            "mean_loudness_dbfs": round(float(np.mean(loudness)), 3) if loudness else -160.0,
            "energy_active_fraction": round(sum(active) / len(active), 4) if active else 0.0,
            "onset_count": len(onsets),
            "mean_spectral_centroid_hz": round(float(np.mean(centroids)), 2) if centroids else 0.0,
        },
    }


def _candidate_payload(claim: Any) -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": candidate.candidate_id,
            "text_ru": candidate.text_ru,
            "raw_cosine": candidate.raw_cosine,
            "decision": candidate.decision,
        }
        for candidate in claim.top_candidates
    ]


def _match_window(
    *,
    source: str | Path,
    stream_id: str,
    epoch: int,
    start_ms: int,
    end_ms: int,
    modality: str,
    record: EmbeddingRecord,
    axes: list[tuple[HypothesisAxis, dict[str, np.ndarray]]],
    policy: MatchPolicy,
    matcher: SemanticMatcher,
    reducer: TemporalEventReducer,
    store: EventStore,
    emit: Callable[[dict[str, Any]], None],
    gated_axis_ids: frozenset[str] = frozenset(),
    music_presence_axis_id: str | None = None,
    additional_evidence: tuple[str, ...] = (),
    iterative_refiner: IterativeHypothesisRefiner | None = None,
    sampling_novelty_score: float | None = None,
    signal_delta_score: float | None = None,
    embedding_novelty: EmbeddingNovelty | None = None,
    on_accepted_claim: Callable[[], None] | None = None,
) -> tuple[int, int, int]:
    evidence = (f"{modality}:{start_ms}-{end_ms}", f"embedding:{record.window_id}")
    event_count = 0
    match_count = 0
    skipped_count = 0
    presence_decision: str | None = None
    presence_candidate: str | None = None
    gate_evidence: tuple[str, ...] = ()
    ordered_axes = (
        sorted(axes, key=lambda item: item[0].axis_id != music_presence_axis_id)
        if music_presence_axis_id is not None
        else axes
    )
    for axis, vectors in ordered_axes:
        if axis.axis_id in gated_axis_ids and not _music_detail_allowed(
            presence_candidate, presence_decision
        ):
            reason = (
                "music_presence_uncertain"
                if presence_decision != "accepted"
                else "music_not_present"
            )
            emit(
                {
                    "record_type": "skipped_match",
                    "level": "L1",
                    "source": _source_label(source),
                    "modality": modality,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "axis_id": axis.axis_id,
                    "reason": reason,
                    "gate": {
                        "axis_id": music_presence_axis_id,
                        "candidate_id": presence_candidate,
                        "decision": presence_decision,
                    },
                    "window_id": record.window_id,
                    "evidence_refs": list(evidence),
                }
            )
            skipped_count += 1
            continue

        axis_evidence: tuple[str, ...] = evidence
        if axis.axis_id in gated_axis_ids:
            axis_evidence = (*evidence, *gate_evidence, *additional_evidence)
        active_axis = axis
        if iterative_refiner is None:
            claim = matcher.match_axis(
                axis,
                record.embedding,
                vectors,
                policy=policy,
                model_revision=record.model_revision,
                evidence_refs=axis_evidence,
            )
        else:
            outcome = iterative_refiner.match(
                axis,
                record.embedding,
                vectors,
                matcher=matcher,
                policy=policy,
                model_revision=record.model_revision,
                evidence_refs=axis_evidence,
            )
            active_axis = outcome.axis
            claim = outcome.selected
            if outcome.report is not None:
                emit(
                    {
                        **outcome.report,
                        "stream_id": stream_id,
                        "epoch": epoch,
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "window_id": record.window_id,
                        "evidence_refs": list(axis_evidence),
                    }
                )
        match_count += 1
        if axis.axis_id == music_presence_axis_id:
            presence_decision = claim.decision
            presence_candidate = claim.candidate_id
            gate_evidence = (
                f"music-presence:{claim.decision}:{claim.candidate_id}:{start_ms}-{end_ms}",
            )
        candidate_rows = (
            [
                {
                    "candidate_id": item.candidate_id,
                    "text_ru": item.text_ru,
                    "decision": item.decision,
                    "raw_cosine": item.raw_cosine,
                    "margin": max(0.0, item.raw_cosine - policy.minimum_similarity),
                }
                for item in claim.supported_candidates
            ]
            if not active_axis.mutually_exclusive and claim.supported_candidates
            else [
                {
                    "candidate_id": claim.candidate_id,
                    "text_ru": claim.text_ru,
                    "decision": claim.decision,
                    "raw_cosine": claim.raw_cosine,
                    "margin": claim.margin,
                }
            ]
        )
        emit(
            {
                "record_type": "window_match",
                "level": "L1",
                "source": _source_label(source),
                "modality": modality,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "axis_id": claim.axis_id,
                "candidate_id": claim.candidate_id,
                "text_ru": claim.text_ru,
                "decision": claim.decision,
                "raw_cosine": claim.raw_cosine,
                "margin": claim.margin,
                "thresholds": {
                    "minimum_similarity": policy.minimum_similarity,
                    "minimum_margin": policy.minimum_margin,
                    "top_k": policy.top_k,
                    "margin_basis": (
                        "similarity_threshold"
                        if not active_axis.mutually_exclusive
                        else "top_candidate_gap"
                    ),
                    "similarity_is_probability": False,
                },
                "top_candidates": _candidate_payload(claim),
                "supported_candidates": candidate_rows,
                "model_revision": claim.model_revision,
                "window_id": record.window_id,
                "evidence_refs": list(axis_evidence),
                **(
                    {
                        "sampling_novelty": {
                            "method_version": "sampling-novelty-v1",
                            "score_definition": (
                                "max(signal_delta_score, "
                                "clip(1 - embedding_cosine_similarity, 0, 1))"
                            ),
                            "score": sampling_novelty_score,
                            "signal_delta_score": signal_delta_score,
                            "embedding_cosine_similarity": (
                                embedding_novelty.cosine_similarity
                                if embedding_novelty is not None
                                else None
                            ),
                            "embedding_novelty_score": (
                                embedding_novelty.novelty_score
                                if embedding_novelty is not None
                                else None
                            ),
                            "embedding_comparable": (
                                embedding_novelty.comparable
                                if embedding_novelty is not None
                                else False
                            ),
                            "embedding_reference_window_id": (
                                embedding_novelty.reference_window_id
                                if embedding_novelty is not None
                                else None
                            ),
                            "similarity_is_probability": False,
                        }
                    }
                    if (
                        sampling_novelty_score is not None
                        or signal_delta_score is not None
                        or embedding_novelty is not None
                    )
                    else {}
                ),
            }
        )
        if claim.decision == "accepted" and on_accepted_claim is not None:
            on_accepted_claim()
        for candidate in candidate_rows:
            match = WindowMatch(
                stream_id=stream_id,
                epoch=epoch,
                start_ms=start_ms,
                end_ms=end_ms,
                axis_id=claim.axis_id,
                candidate_id=str(candidate["candidate_id"]),
                text_ru=(candidate["text_ru"] if isinstance(candidate["text_ru"], str) else None),
                decision=str(candidate["decision"]),
                raw_cosine=cast(float, candidate["raw_cosine"]),
                margin=cast(float, candidate["margin"]),
                modality=modality,
                evidence_refs=axis_evidence,
                window_id=record.window_id,
                model_revision=claim.model_revision,
                candidate_independent=not active_axis.mutually_exclusive,
            )
            event = reducer.ingest(match)
            if event is not None:
                store.append(event, expected_revision=event.revision - 1)
                emit({"record_type": "event", **event.to_dict()})
                event_count += 1
    return match_count, event_count, skipped_count


def _music_detail_allowed(candidate_id: str | None, decision: str | None) -> bool:
    """Only accepted positive music-presence claims open the detailed axes."""
    return decision == "accepted" and candidate_id == "music_present"


@_sample_process_rss
def analyze_media(
    source: str | Path,
    model: dict[str, Any],
    models_dir: Path,
    *,
    stream_id: str,
    epoch: int = 0,
    threads: int,
    window_ms: int,
    policy: MatchPolicy,
    levels: frozenset[str],
    cache_dir: Path | None = None,
    event_database: Path | str = ":memory:",
    emit: Callable[[dict[str, Any]], None],
    iterative_axis: str | None = None,
    speech_enabled: bool = False,
    narrator_mode: Literal["qwen", "template"] = "qwen",
    sampling_profile: SamplingProfile = "standard",
    vision_profile: Literal["standard", "compact"] = "standard",
    prefetch_overflow_policy: OverflowPolicy | None = None,
    prefetch_capacity: int | None = None,
    stop_event: Event | None = None,
    runtime_load_controller: RuntimeLoadController | None = None,
    load_source_id: str | None = None,
    embedding_provider_pool: EmbeddingProviderPool | None = None,
) -> dict[str, Any]:
    """Decode local media, run actual CPU embeddings, rank claims, and emit JSONL rows."""
    if window_ms < 250:
        raise ValueError("window_ms must be at least 250")
    if epoch < 0:
        raise ValueError("epoch must be non-negative")
    if not levels or not levels.issubset({"L0", "L1", "L2", "L3"}):
        raise ValueError("levels must contain one or more of L0, L1, L2, and L3")
    if narrator_mode not in {"qwen", "template"}:
        raise ValueError("narrator_mode must be qwen or template")
    if sampling_profile not in {"standard", "adaptive"}:
        raise ValueError("sampling_profile must be standard or adaptive")
    if vision_profile not in {"standard", "compact"}:
        raise ValueError("vision_profile must be standard or compact")
    live_source = (
        isinstance(source, str) and urlsplit(source).scheme.lower() in {"rtsp", "rtsps"}
    )
    if prefetch_overflow_policy is None:
        prefetch_overflow_policy = "drop_oldest" if live_source else "block"
    if prefetch_overflow_policy not in {"block", "drop_newest", "drop_oldest"}:
        raise ValueError("unsupported prefetch overflow policy")
    if live_source and prefetch_overflow_policy == "block":
        raise ValueError("live RTSP sources require a non-blocking overflow policy")
    if prefetch_capacity is not None and prefetch_capacity < 1:
        raise ValueError("prefetch_capacity must be positive")
    if isinstance(source, Path) and not source.is_file():
        raise FileNotFoundError(source)

    started = time.perf_counter()
    media = inspect_media(source)
    source_duration_ms = _source_duration_ms(source)
    active_levels = _active_levels(levels)
    provider_started = time.perf_counter()
    provider_kwargs: dict[str, Any] = {
        "cache_dir": cache_dir,
        "threads": threads,
        "enabled_modalities": set(media.available_modalities),
    }
    provider = (
        embedding_provider_pool.get_or_create(model, models_dir, **provider_kwargs)
        if embedding_provider_pool is not None
        else EmbeddingProvider(model, models_dir, **provider_kwargs)
    )
    shared_embedding_dispatcher: SharedEmbeddingDispatcher | None = (
        embedding_provider_pool.dispatcher_for(provider)
        if embedding_provider_pool is not None
        else None
    )
    profiles = load_profiles(
        Path(__file__).resolve().parents[2] / "configs" / "hypotheses",
        expected_model_revision=str(model["revision"]),
    )
    vectors_by_profile = {
        profile.profile_id: encode_profile_candidates(profile, provider) for profile in profiles
    }
    profile_embedding_ms = (time.perf_counter() - provider_started) * 1000
    music_profile = next(profile for profile in profiles if profile.profile_id == "music")
    music_presence_axis_id = "music_presence"
    music_detail_axis_ids = frozenset(
        axis.axis_id for axis in music_profile.axes if axis.axis_id != music_presence_axis_id
    )

    axes_by_modality: dict[str, list[tuple[HypothesisAxis, dict[str, np.ndarray]]]] = {
        "audio": [],
        "image": [],
    }
    for profile in profiles:
        for axis in profile.axes:
            if axis.modality not in axes_by_modality:
                continue
            candidate_records = vectors_by_profile[profile.profile_id][axis.axis_id]
            axes_by_modality[axis.modality].append(
                (
                    axis,
                    {
                        candidate_id: record.embedding
                        for candidate_id, record in candidate_records.items()
                    },
                )
            )

    iterative_refiner: IterativeHypothesisRefiner | None = None
    if iterative_axis is not None:
        selected_axes = [
            axis
            for axes in axes_by_modality.values()
            for axis, _vectors in axes
            if axis.axis_id == iterative_axis
        ]
        if len(selected_axes) != 1:
            raise ValueError(
                f"iterative axis {iterative_axis!r} must identify exactly one loaded axis"
            )
        lock_path = Path(__file__).resolve().parents[2] / "models.lock.json"
        qwen_model = json.loads(lock_path.read_text(encoding="utf-8"))["models"]["qwen3_0_6b"]
        proposer = QwenHypothesisProposer(
            qwen_model,
            models_dir,
            Path(__file__).resolve().parents[2],
            threads=threads,
            max_candidates=6,
            timeout_seconds=10.0,
        )
        iterative_refiner = IterativeHypothesisRefiner(
            axis_id=iterative_axis,
            encoder=provider,
            proposer=proposer,
            cpu_budget_ms=15_000,
        )

    reducer = TemporalEventReducer(min_repeats=2, max_gap_ms=window_ms)
    matcher = SemanticMatcher()
    sampling_controller = AdaptiveSamplingController(
        profile=sampling_profile,
        window_ms=window_ms,
    )
    per_stage_ms = {
        "audio_consumer_work": 0.0,
        "video_consumer_work": 0.0,
        "shared_media_interleave": 0.0,
        "embedding_inference": 0.0,
        "embedding_worker_elapsed": 0.0,
        "embedding_result_apply": 0.0,
        "l1_match_and_reduce": 0.0,
        "l2_state_refinement": 0.0,
        "l3_narration": 0.0,
    }
    emitted_events = 0
    emitted_matches = 0
    skipped_matches = 0
    processed_intervals: list[tuple[int, int]] = []
    processed_intervals_lock = RLock()
    latest_events: dict[str, TimelineEvent] = {}
    speech_available = speech_enabled and "audio" in media.available_modalities
    required_modalities: set[Literal["audio", "video", "speech"]] = {"audio", "video"}
    if speech_enabled:
        required_modalities.add("speech")
    watermark = WatermarkTracker(
        stream_id,
        epoch=epoch,
        required_modalities=required_modalities,
    )
    load_controller = runtime_load_controller or RuntimeLoadController()
    load_source_id = load_source_id or stream_id
    host_metrics_available = False
    runtime_load_observation_count = 0
    last_runtime_load_observation = 0.0
    ingest_telemetry = RingDecodeTelemetry()
    audio_prefetch_capacity = prefetch_capacity or AUDIO_PREFETCH_CAPACITY
    video_prefetch_capacity = prefetch_capacity or VIDEO_PREFETCH_CAPACITY
    prefetch_telemetry = {
        "audio": PrefetchTelemetry(capacity=audio_prefetch_capacity),
        "video": PrefetchTelemetry(capacity=video_prefetch_capacity),
    }
    remote_source = isinstance(source, str) and "://" in source
    if remote_source:
        prefetch_telemetry["shared"] = PrefetchTelemetry(
            capacity=audio_prefetch_capacity + video_prefetch_capacity
        )
    capture_cursors: dict[Modality, int] = {"audio": 0, "video": 0}
    capture_reported_ms: dict[Modality, int] = {"audio": 0, "video": 0}
    capture_first_seen: set[Modality] = set()
    semantic_modalities = set(media.available_modalities) & {"audio", "video"}
    semantic_levels: tuple[Level, ...] = ("L1", "L2", "L3")
    semantic_coverage_stages: tuple[CoverageStage, ...] = ("D", "R")
    semantic_origin_gap_marked = not semantic_modalities
    semantic_first_window_starts: dict[Modality, int] = {}
    relation_validator = CrossModalRelationValidator()
    relation_assessment: dict[str, object] = {}
    progress_end_ms = 0
    video_level_cursor = 0
    video_level_cursor_lock = Lock()
    l1_worker: BoundedL1Worker | None = None
    speech_worker: BoundedSpeechWorker | None = None
    progressive_workers: LiveLevelWorkers | None = None
    deferred_speech_tasks: deque[SpeechTask] = deque()
    deferred_speech_capacity = 2
    speech_admission_drop_count = 0
    next_l1_job_id = 0
    publish_lock = RLock()
    progress_lock = RLock()
    capture_state_lock = RLock()
    l1_frontier_lock = RLock()
    l1_processed_frontiers: dict[str, int] = {}
    live_pending_coverage: list[tuple[int, int]] = []
    live_coverage_lock = RLock()

    def observe_runtime_load(*, force: bool = False) -> None:
        nonlocal host_metrics_available
        nonlocal last_runtime_load_observation, runtime_load_observation_count
        now = time.perf_counter()
        if not force and now - last_runtime_load_observation < 0.25:
            return
        last_runtime_load_observation = now

        queue_candidates = [
            (telemetry.current_depth, telemetry.capacity)
            for telemetry in prefetch_telemetry.values()
        ]
        if embedding_worker is not None:
            queue_candidates.append(
                (embedding_worker.outstanding, embedding_worker.queue_capacity)
            )
        if l1_worker is not None:
            queue_candidates.append((l1_worker.outstanding, l1_worker.queue_capacity))
        if speech_worker is not None:
            queue_candidates.append(
                (
                    speech_worker.outstanding + len(deferred_speech_tasks),
                    speech_worker.admission_capacity + deferred_speech_capacity,
                )
            )
        if progressive_workers is not None:
            queue_candidates.extend(progressive_workers.queue_loads())
        queue_depth, queue_capacity = max(
            queue_candidates,
            key=lambda item: item[0] / item[1],
            default=(0, 64),
        )
        with progress_lock:
            source_horizon = progress_end_ms
        snapshot = watermark.snapshot(through_ms=source_horizon)
        source_lag_ms = max(0, source_horizon - snapshot.E_ms)
        try:
            memory_limit_bytes = max(0, int(os.environ.get("SHSD_MEMORY_LIMIT_BYTES", "0")))
        except ValueError:
            memory_limit_bytes = 0
        sampler = _ACTIVE_RESOURCE_SAMPLER.get()
        if sampler is None:
            sample = LoadSample(
                queue_depth=queue_depth,
                queue_capacity=queue_capacity,
                source_lag_ms=source_lag_ms,
                memory_limit_bytes=memory_limit_bytes,
            )
        else:
            host_metrics_available = host_metrics_available or sampler.available
            sample = sampler.load_sample(
                queue_depth=queue_depth,
                queue_capacity=queue_capacity,
                source_lag_ms=source_lag_ms,
                memory_limit_bytes=memory_limit_bytes,
            )
        load_controller.observe(sample, source_id=load_source_id)
        runtime_load_observation_count += 1
        if deferred_speech_tasks:
            flush_deferred_speech()

    def publish(record: dict[str, Any]) -> None:
        progressive_event: TimelineEvent | None = None
        with publish_lock:
            if record.get("record_type") == "event":
                event_data = {key: value for key, value in record.items() if key != "record_type"}
                event = TimelineEvent.from_dict(event_data)
                latest_events[event.event_id] = event
                if (
                    event.level in {"L0", "L1"}
                    and event.state == "committed"
                    and progressive_workers is not None
                ):
                    progressive_event = event
            emit(record)
        if progressive_event is not None and progressive_workers is not None:
            progressive_workers.submit_event(progressive_event)

    def mark_live_coverage(
        level: str,
        stage: str,
        start_ms: int,
        end_ms: int,
        status: str,
        reason: str | None,
    ) -> None:
        watermark.mark_revisioned(
            cast(CoverageStage, stage),
            start_ms,
            end_ms,
            cast(CoverageStatus, status),
            level=cast(Level, level),
            reason=reason,
        )
        emit_watermark()

    for modality in media.unavailable_modalities:
        if source_duration_ms is not None:
            watermark.mark(
                "C",
                0,
                source_duration_ms,
                "unavailable",
                modality=modality,
                reason="track_unavailable",
            )
            watermark.mark(
                "E",
                0,
                source_duration_ms,
                "unavailable",
                modality=modality,
                reason="track_unavailable",
            )
    if speech_enabled and not speech_available and source_duration_ms is not None:
        for stage in ("C", "E"):
            watermark.mark(
                stage,
                0,
                source_duration_ms,
                "unavailable",
                modality="speech",
                reason="audio_unavailable",
            )

    def emit_watermark(
        through_ms: int | None = None, *, advance_source_horizon: bool = False
    ) -> None:
        nonlocal progress_end_ms
        with progress_lock:
            if advance_source_horizon and through_ms is not None:
                progress_end_ms = max(progress_end_ms, through_ms)
            if source_duration_ms is None and progress_end_ms > 0:
                unavailable_modalities: list[tuple[CoverageModality, str]] = [
                    (modality, "track_unavailable")
                    for modality in media.unavailable_modalities
                ]
                if speech_enabled and not speech_available:
                    unavailable_modalities.append(("speech", "audio_unavailable"))
                for modality, reason in unavailable_modalities:
                    for stage in ("C", "E"):
                        watermark.mark_uncovered(
                            stage,
                            0,
                            progress_end_ms,
                            "unavailable",
                            modality=modality,
                            reason=reason,
                        )
            snapshot = watermark.snapshot(through_ms=progress_end_ms)
            publish(
                {
                    "record_type": "watermark",
                    "schema_version": 1,
                    "source_end_ms": progress_end_ms,
                    "watermarks": snapshot.to_dict(),
                    "backlog_ms": {
                        level: max(0, progress_end_ms - snapshot.R_ms[level])
                        for level in ("L1", "L2", "L3")
                    },
                }
            )

    def mark_ingest_capture(
        modality: Modality,
        start_ms: int,
        end_ms: int,
        status: Literal["done", "dropped"],
        reason: str | None,
    ) -> None:
        start = max(0, start_ms)
        end = max(start + 1, end_ms)
        emit_progress = False
        with capture_state_lock:
            if modality not in capture_first_seen:
                capture_first_seen.add(modality)
                _mark_initial_capture_gap(watermark, modality, start)
                if start > 0:
                    watermark.mark_uncovered(
                        "E",
                        0,
                        start,
                        "gap",
                        modality=modality,
                        reason="source_timeline_offset",
                    )
            watermark.mark("C", start, end, status, modality=modality, reason=reason)
            capture_cursors[modality] = max(capture_cursors[modality], end)
            if end - capture_reported_ms[modality] >= 1_000:
                capture_reported_ms[modality] = end
                emit_progress = True
        if emit_progress:
            emit_watermark(end, advance_source_horizon=True)

    def get_capture_cursor(modality: Modality) -> int:
        with capture_state_lock:
            return capture_cursors[modality]

    def mark_prefetch_drop(modality: Modality, item: object, reason: str) -> None:
        if isinstance(item, CaptureSpan):
            mark_ingest_capture(item.modality, item.start_ms, item.end_ms, item.status, item.reason)
            return
        _mark_prefetch_drop_coverage(
            watermark, modality, item, reason, speech_available=speech_available
        )

    def mark_media(modality: Modality, start_ms: int, end_ms: int) -> None:
        if end_ms <= start_ms:
            return
        watermark.mark("C", start_ms, end_ms, "done", modality=modality)
        watermark.mark("E", start_ms, end_ms, "done", modality=modality)

    def mark_semantic_origin(modality: Modality | None, start_ms: int) -> None:
        nonlocal semantic_origin_gap_marked
        if modality is None or modality not in semantic_modalities:
            return
        initial_gap_ms = 0
        with processed_intervals_lock:
            semantic_first_window_starts.setdefault(modality, start_ms)
            if (
                not semantic_origin_gap_marked
                and semantic_modalities.issubset(semantic_first_window_starts)
            ):
                initial_gap_ms = min(
                    semantic_first_window_starts[item] for item in semantic_modalities
                )
                semantic_origin_gap_marked = True
        if initial_gap_ms > 0:
            for level in semantic_levels:
                for stage in semantic_coverage_stages:
                    watermark.mark_revisioned(
                        stage,
                        0,
                        initial_gap_ms,
                        "gap",
                        level=level,
                        reason="initial_semantic_coverage",
                    )

    def mark_window_draft(
        start_ms: int,
        end_ms: int,
        *,
        modality: Modality | None = None,
        l1_status: CoverageStatus | None = None,
        l1_reason: str | None = None,
    ) -> None:
        nonlocal video_level_cursor
        with processed_intervals_lock:
            processed_intervals.append((start_ms, end_ms))
        if progressive_workers is not None and "L2" in active_levels:
            with live_coverage_lock:
                live_pending_coverage.append((start_ms, end_ms))
        mark_semantic_origin(modality, start_ms)
        if l1_status is None:
            l1_status = "done" if "L1" in active_levels else "skipped"
        if l1_status == "skipped" and l1_reason is None:
            l1_reason = "level_not_requested" if "L1" not in active_levels else "not_processed"
        for level in semantic_levels:
            if level == "L1":
                watermark.mark_revisioned(
                    "D",
                    start_ms,
                    end_ms,
                    l1_status,
                    level=level,
                    reason=l1_reason,
                )
                # A completed window has a final L1 match decision even when
                # an aggregated event may receive later revisions.
                watermark.mark_revisioned(
                    "R",
                    start_ms,
                    end_ms,
                    l1_status,
                    level=level,
                    reason=l1_reason,
                )
                if modality == "video":
                    with video_level_cursor_lock:
                        video_level_cursor = max(video_level_cursor, end_ms)
            elif level not in active_levels:
                watermark.mark_revisioned(
                    "D",
                    start_ms,
                    end_ms,
                    "skipped",
                    level=level,
                    reason="level_not_requested",
                )
                if progressive_workers is not None:
                    watermark.mark_revisioned(
                        "R",
                        start_ms,
                        end_ms,
                        "skipped",
                        level=level,
                        reason="level_not_requested",
                    )
            elif level == "L2" and progressive_workers is not None:
                watermark.mark_revisioned("D", start_ms, end_ms, "done", level="L2")

    embedding_worker: BoundedEmbeddingWorker | None = None
    embedding_handlers: dict[int, Callable[[EmbeddingRecord], None]] = {}
    next_embedding_job_id = 0

    def dispatch_l1_work(run: Callable[[], None]) -> None:
        nonlocal next_l1_job_id
        if l1_worker is None:
            run()
            return
        job_id = next_l1_job_id
        next_l1_job_id += 1
        l1_worker.submit(L1Work(job_id=job_id, run=run))

    def advance_live_levels(modality: str, end_ms: int) -> None:
        """Commit stable L1 events and enqueue coverage after each live window."""
        if progressive_workers is None or "L2" not in active_levels:
            return
        with l1_frontier_lock:
            l1_processed_frontiers[modality] = max(
                l1_processed_frontiers.get(modality, 0), end_ms
            )
            if not semantic_modalities.issubset(l1_processed_frontiers):
                return
            stable_horizon = min(
                l1_processed_frontiers[item] for item in semantic_modalities
            ) - reducer.max_gap_ms
        if stable_horizon <= 0:
            return

        with publish_lock:
            stable_events = sorted(
                (
                    event
                    for event in latest_events.values()
                    if event.level == "L1"
                    and event.state != "committed"
                    and event.end_ms <= stable_horizon
                ),
                key=lambda event: (event.start_ms, event.end_ms, event.event_id),
            )
        for event in stable_events:
            committed = replace(
                event,
                revision=event.revision + 1,
                state="committed",
                supersedes_revision=event.revision,
                updated_at_utc=datetime.now(UTC).isoformat(),
            )
            store.append(committed, expected_revision=event.revision)
            publish({"record_type": "event", **committed.to_dict()})

        with live_coverage_lock:
            eligible = tuple(
                item for item in live_pending_coverage if item[1] <= stable_horizon
            )
            if eligible and progressive_workers.submit_coverage(eligible):
                eligible_set = set(eligible)
                live_pending_coverage[:] = [
                    item for item in live_pending_coverage if item not in eligible_set
                ]

    def process_l1_window(
        record: EmbeddingRecord,
        *,
        start_ms: int,
        end_ms: int,
        modality: str,
        axes: list[tuple[HypothesisAxis, dict[str, np.ndarray]]],
        signal_delta_score: float | None = None,
        gated_axis_ids: frozenset[str] = frozenset(),
        music_presence_axis_id: str | None = None,
        additional_evidence: tuple[str, ...] = (),
    ) -> None:
        nonlocal emitted_matches, emitted_events, skipped_matches
        l1_started = time.perf_counter()
        embedding_novelty: EmbeddingNovelty | None = None
        sampling_novelty_score = signal_delta_score
        accepted_state = False
        track_modality = "video" if modality == "image" else modality
        if sampling_profile == "adaptive":
            embedding_novelty = sampling_controller.compare_accepted_embedding(
                track_modality,
                record.embedding,
                model_revision=record.model_revision,
                preprocess_version=record.input_preprocess_version,
                window_id=record.window_id,
            )
            novelty_components = [
                score
                for score in (signal_delta_score, embedding_novelty.novelty_score)
                if score is not None
            ]
            sampling_novelty_score = max(novelty_components) if novelty_components else None

        def accept_current_embedding() -> None:
            nonlocal accepted_state
            accepted_state = True

        match_count, event_count, skipped_count = _match_window(
            source=source,
            stream_id=stream_id,
            epoch=epoch,
            start_ms=start_ms,
            end_ms=end_ms,
            modality=modality,
            record=record,
            axes=axes,
            policy=policy,
            matcher=matcher,
            reducer=reducer,
            store=store,
            emit=publish,
            gated_axis_ids=gated_axis_ids,
            music_presence_axis_id=music_presence_axis_id,
            additional_evidence=additional_evidence,
            iterative_refiner=iterative_refiner,
            sampling_novelty_score=sampling_novelty_score,
            signal_delta_score=signal_delta_score,
            embedding_novelty=embedding_novelty,
            on_accepted_claim=accept_current_embedding,
        )
        if accepted_state and sampling_profile == "adaptive":
            sampling_controller.accept_embedding(
                track_modality,
                record.embedding,
                model_revision=record.model_revision,
                preprocess_version=record.input_preprocess_version,
                window_id=record.window_id,
            )
        emitted_matches += match_count
        emitted_events += event_count
        skipped_matches += skipped_count
        mark_window_draft(
            start_ms,
            end_ms,
            modality="audio" if modality == "audio" else "video",
        )
        advance_live_levels("audio" if modality == "audio" else "video", end_ms)
        emit_watermark()
        per_stage_ms["l1_match_and_reduce"] += (time.perf_counter() - l1_started) * 1000

    def apply_embedding_result(result: EmbeddingResult) -> None:
        handler = embedding_handlers.pop(result.job_id, None)
        if handler is None:
            raise RuntimeError(f"unknown embedding worker job {result.job_id}")
        per_stage_ms["embedding_inference"] += result.inference_ms
        per_stage_ms["embedding_worker_elapsed"] += result.elapsed_ms
        if result.error is not None or result.record is None:
            raise RuntimeError(
                f"embedding job {result.job_id} failed: {result.error or 'no record returned'}"
            )
        started_apply = time.perf_counter()
        handler(result.record)
        per_stage_ms["embedding_result_apply"] += (time.perf_counter() - started_apply) * 1000

    def dispatch_embedding(
        encode: Callable[[], EmbeddingRecord],
        handler: Callable[[EmbeddingRecord], None],
    ) -> None:
        nonlocal next_embedding_job_id
        if embedding_worker is None:
            started_encode = time.perf_counter()
            record = encode()
            per_stage_ms["embedding_inference"] += (time.perf_counter() - started_encode) * 1000
            started_apply = time.perf_counter()
            handler(record)
            per_stage_ms["embedding_result_apply"] += (time.perf_counter() - started_apply) * 1000
            return
        job_id = next_embedding_job_id
        next_embedding_job_id += 1
        embedding_handlers[job_id] = handler
        try:
            embedding_worker.submit(
                EmbeddingJob(job_id=job_id, encode=encode),
                apply_embedding_result,
            )
        except Exception:
            embedding_handlers.pop(job_id, None)
            raise

    def finish_audio_embedding(
        record: EmbeddingRecord,
        *,
        start_ms: int,
        end_ms: int,
        audio_deltas: list[SignalObservation],
        signal_delta_score: float | None,
    ) -> None:
        watermark.mark("E", start_ms, end_ms, "done", modality="audio")
        if "L0" in levels:
            publish(_record_embedding(record, start_ms=start_ms, end_ms=end_ms, source=source))
        if "L1" in active_levels:
            dispatch_l1_work(
                lambda: process_l1_window(
                    record,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    modality="audio",
                    axes=axes_by_modality["audio"],
                    signal_delta_score=signal_delta_score,
                    gated_axis_ids=music_detail_axis_ids,
                    music_presence_axis_id=music_presence_axis_id,
                    additional_evidence=tuple(
                        f"observation:{item.subtype}:{item.start_ms}-{item.end_ms}"
                        for item in audio_deltas
                    )
                    if "L0" in active_levels
                    else (),
                )
            )
        else:
            mark_window_draft(start_ms, end_ms, modality="audio")
            emit_watermark()

    def finish_video_embedding(
        record: EmbeddingRecord,
        *,
        start_ms: int,
        end_ms: int,
        sample_end_ms: int,
        signal_delta_score: float | None,
    ) -> None:
        if sample_end_ms > start_ms:
            watermark.mark("E", start_ms, sample_end_ms, "done", modality="video")
        if "L0" in active_levels:
            publish(_record_embedding(record, start_ms=start_ms, end_ms=end_ms, source=source))
        if "L1" in active_levels:
            dispatch_l1_work(
                lambda: process_l1_window(
                    record,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    modality="image",
                    axes=axes_by_modality["image"],
                    signal_delta_score=signal_delta_score,
                )
            )
        else:
            mark_window_draft(start_ms, end_ms, modality="video")
            emit_watermark()

    publish(
        {
            "record_type": "analysis",
            "schema_version": 1,
            "source": _source_label(source),
            "source_duration_ms": source_duration_ms,
            "stream_id": stream_id,
            "epoch": epoch,
            "levels": sorted(levels),
            "active_levels": sorted(active_levels),
            "runtime_target": "cpu",
            "threads": threads,
            "window_ms": window_ms,
            "modalities": {
                "available": list(media.available_modalities),
                "unavailable": list(media.unavailable_modalities),
                "speech": "enabled"
                if speech_available
                else ("unavailable" if speech_enabled else "disabled"),
            },
            "embedding_model_revision": model["revision"],
            "profile_fingerprints": {
                profile.profile_id: profile.candidate_fingerprint() for profile in profiles
            },
            "decision_policy": {
                "minimum_similarity": policy.minimum_similarity,
                "minimum_margin": policy.minimum_margin,
                "top_k": policy.top_k,
                "similarity_is_probability": False,
                "calibration": "provisional; inspect raw cosine and abstentions",
            },
            "music_detail_gate": {
                "axis_id": music_presence_axis_id,
                "required_candidate": "music_present",
                "required_decision": "accepted",
            },
            "iterative_hypothesis_axis": iterative_axis,
            "iterative_hypothesis_enabled": iterative_refiner is not None,
            "narrator_mode": narrator_mode if "L3" in active_levels else "off",
            "sampling_profile": sampling_profile,
            "vision_profile": vision_profile,
            "vision_max_soft_tokens": (
                DEFAULT_IMAGE_SOFT_TOKENS
                if vision_profile == "standard"
                else COMPACT_IMAGE_SOFT_TOKENS
            ),
            "embedding_worker": {
                "enabled": iterative_refiner is None,
                "queue_capacity": 2,
                "execution": "serial_background" if iterative_refiner is None else "inline",
            },
            "prefetch_overflow_policy": prefetch_overflow_policy,
            "prefetch_capacity": prefetch_capacity,
        }
    )
    emit_watermark(0)

    with EventStore(event_database) as store:
        store.begin_epoch(stream_id, epoch)
        speech_worker = None
        speech_assembler: SpeechWindowAssembler | None = None
        speech_started = time.perf_counter()
        speech_result_count = 0
        speech_error_count = 0
        speech_dropped_count = 0
        speech_worker_report: dict[str, Any] = {"enabled": False}

        def publish_speech_result(result: SpeechResult) -> None:
            nonlocal speech_result_count, speech_error_count, speech_dropped_count
            status = {
                "complete": "partial",
                "failed": "failed",
                "dropped": "dropped",
            }[result.status]
            segment_id = hashlib.sha256(
                f"{stream_id}:{epoch}:{result.start_ms}:{result.end_ms}".encode()
            ).hexdigest()[:24]
            record: dict[str, Any] = {
                "record_type": "speech_segment",
                "schema_version": 1,
                "stream_id": stream_id,
                "epoch": epoch,
                "segment_id": segment_id,
                "revision": 1,
                "status": status,
                "start_ms": result.start_ms,
                "end_ms": result.end_ms,
                "text": result.text or "",
                "language": "ru",
                "language_source": "gigaam_v3_model_family",
                "source": _source_label(source),
                "model": {
                    "name": "GigaAM-v3-e2e-ctc",
                    "repo_id": "ai-sage/GigaAM-v3",
                    "revision": "cec030b4c4f35d928e4a9044a3bdb29ebd499fac",
                    "api_revision": "7447938d791c4f3e643386ee22c33777004293a5",
                    "device": "cpu",
                },
                "timestamp_basis": "resampled_audio_window_pts",
            }
            if result.error:
                record["error"] = result.error
            store.append_speech_segment(stream_id, epoch, record)
            publish(record)
            if result.status == "complete":
                speech_result_count += 1
                watermark.mark("E", result.start_ms, result.end_ms, "done", modality="speech")
            elif result.status == "dropped":
                speech_dropped_count += 1
                watermark.mark(
                    "E",
                    result.start_ms,
                    result.end_ms,
                    "dropped",
                    modality="speech",
                    reason=result.error or "asr_queue_full",
                )
            else:
                speech_error_count += 1
                watermark.mark(
                    "E",
                    result.start_ms,
                    result.end_ms,
                    "failed",
                    modality="speech",
                    reason="asr_failed",
                )
            emit_watermark()

        def submit_speech(task: SpeechTask) -> None:
            nonlocal speech_admission_drop_count
            if speech_worker is None:
                return
            decision = load_controller.admit(WorkPriority.L2_ASR)
            if decision.admitted and speech_worker.submit(task):
                return
            reason = decision.reason or speech_worker.last_submit_reason or "asr_queue_full"
            if reason == "load_critical" or reason == "asr_queue_full":
                if len(deferred_speech_tasks) < deferred_speech_capacity:
                    deferred_speech_tasks.append(task)
                    return
            speech_admission_drop_count += 1
            publish_speech_result(
                SpeechResult(task.start_ms, task.end_ms, None, "dropped", reason)
            )

        def flush_deferred_speech() -> None:
            nonlocal speech_admission_drop_count
            if speech_worker is None:
                return
            while deferred_speech_tasks:
                task = deferred_speech_tasks[0]
                decision = load_controller.admit(WorkPriority.L2_ASR)
                if not decision.admitted:
                    return
                if speech_worker.submit(task):
                    deferred_speech_tasks.popleft()
                    continue
                reason = speech_worker.last_submit_reason or "asr_queue_full"
                if reason == "asr_queue_full":
                    return
                deferred_speech_tasks.popleft()
                speech_admission_drop_count += 1
                publish_speech_result(
                    SpeechResult(task.start_ms, task.end_ms, None, "dropped", reason)
                )

        if speech_available:
            speech_worker = BoundedSpeechWorker(
                GigaAMTranscriber(models_dir / "gigaam_v3_e2e_ctc"),
                queue_capacity=2,
                result_capacity=8,
                load_controller=load_controller,
            )
            speech_assembler = SpeechWindowAssembler(window_ms=ASR_WINDOW_MS)

        video_prefetch: Generator[CaptureSpan | _SelectedVideoWork, None, None] | None = None
        audio_prefetch: Generator[CaptureSpan | tuple[int, int, np.ndarray], None, None] | None = (
            None
        )
        timed_sources: list[Iterable[tuple[int, str, object]]] = []

        def mark_shared_prefetch_drop(item: object, reason: str) -> None:
            _ready_ms, modality_name, payload = cast(tuple[int, str, object], item)
            if modality_name in {"audio", "video"}:
                mark_prefetch_drop(cast(Modality, modality_name), payload, reason)

        shared_prefetch: Generator[tuple[int, str, object], None, None] | None = None
        if remote_source:
            shared_items = _timed_shared_media_work(
                iter_decoded_media_from_ring(
                    source,
                    stream_id=stream_id,
                    modalities=media.available_modalities,
                    telemetry=ingest_telemetry,
                    load_controller=load_controller,
                    stop_event=stop_event,
                ),
                modalities=set(media.available_modalities),
                window_ms=window_ms,
                source_duration_ms=source_duration_ms,
                sampling=sampling_controller,
                load_controller=load_controller,
            )
            shared_prefetch = iter_bounded_prefetch(
                lambda: shared_items,
                telemetry=prefetch_telemetry["shared"],
                overflow_policy=prefetch_overflow_policy,
                on_drop=mark_shared_prefetch_drop,
            )
            timed_sources.append(shared_prefetch)
        else:
            if "video" in media.available_modalities:
                video_items = _selected_video_items(
                    iter_decoded_frames_from_ring(
                        source,
                        stream_id=stream_id,
                        modality="video",
                        telemetry=ingest_telemetry,
                        load_controller=load_controller,
                        stop_event=stop_event,
                    ),
                    window_ms=window_ms,
                    source_duration_ms=source_duration_ms,
                    sampling=sampling_controller,
                    load_controller=load_controller,
                )
                video_prefetch = iter_bounded_prefetch(
                    lambda: video_items,
                    telemetry=prefetch_telemetry["video"],
                    overflow_policy=prefetch_overflow_policy,
                    on_drop=lambda item, reason: mark_prefetch_drop("video", item, reason),
                )

            if "audio" in media.available_modalities:
                audio_items = _audio_windows(
                    iter_decoded_frames_from_ring(
                        source,
                        stream_id=stream_id,
                        modality="audio",
                        telemetry=ingest_telemetry,
                        load_controller=load_controller,
                        stop_event=stop_event,
                    ),
                    window_ms,
                )
                audio_prefetch = iter_bounded_prefetch(
                    lambda: audio_items,
                    telemetry=prefetch_telemetry["audio"],
                    overflow_policy=prefetch_overflow_policy,
                    on_drop=lambda item, reason: mark_prefetch_drop("audio", item, reason),
                )

            if audio_prefetch is not None:
                timed_sources.append(_timed_audio_work(audio_prefetch))
            if video_prefetch is not None:
                timed_sources.append(_timed_video_work(video_prefetch))
        media_admission_telemetry = MediaAdmissionTelemetry(source_count=len(timed_sources))

        previous_audio_observations: list[SignalObservation] | None = None
        last_signal: tuple[int, np.ndarray] | None = None
        video_capture_cursor = get_capture_cursor("video")
        video_embedding_cursor = 0
        video_embedding_gap_reason: str | None = None
        embedding_worker_report: dict[str, Any] = {
            "enabled": iterative_refiner is None,
            "execution": "serial_background" if iterative_refiner is None else "inline",
        }
        l1_worker_report: dict[str, Any] = {
            "enabled": False,
            "execution": "inline",
        }
        shared_consumer_started = time.perf_counter()
        if iterative_refiner is None:
            embedding_worker = BoundedEmbeddingWorker(
                queue_capacity=2,
                load_controller=load_controller,
                shared_dispatcher=shared_embedding_dispatcher,
                source_id=load_source_id,
            )
            if "L1" in active_levels or "L0" in active_levels:
                l1_worker = BoundedL1Worker(
                    queue_capacity=4,
                    load_controller=load_controller,
                )
        if remote_source and "L2" in active_levels:
            def create_live_narrator() -> Any:
                from shsd.captions.narrator import QwenNarrator, TemplateNarrator

                if narrator_mode == "template":
                    return TemplateNarrator()
                lock_path = Path(__file__).resolve().parents[2] / "models.lock.json"
                qwen_model = json.loads(lock_path.read_text(encoding="utf-8"))["models"][
                    "qwen3_0_6b"
                ]
                return QwenNarrator(
                    qwen_model,
                    models_dir,
                    Path(__file__).resolve().parents[2],
                    threads=threads,
                    max_tokens=96,
                )

            progressive_workers = LiveLevelWorkers(
                store=store,
                load_controller=load_controller,
                emit=publish,
                mark_coverage=mark_live_coverage,
                make_requests=lambda events: _narration_batches(
                    events, stream_id=stream_id, epoch=epoch
                ),
                narrator_factory=create_live_narrator,
                l3_enabled="L3" in active_levels,
            )
        for timestamp_ms, work_modality, payload in iter_merge_by_key(
            timed_sources,
            key=lambda item: item[0],
            priority=lambda item: (
                int(WorkPriority.CAPTURE)
                if isinstance(item[2], CaptureSpan)
                else int(WorkPriority.L0_SIGNAL)
            ),
            telemetry=media_admission_telemetry,
        ):
            if embedding_worker is not None:
                embedding_worker.drain(apply_embedding_result)
            observe_runtime_load()
            if stop_event is not None and stop_event.is_set():
                if work_modality in {"audio", "video"}:
                    mark_prefetch_drop(cast(Modality, work_modality), payload, "stream_stopped")
                break
            if work_modality == "audio":
                audio_item = cast(CaptureSpan | tuple[int, int, np.ndarray], payload)
                if isinstance(audio_item, CaptureSpan):
                    mark_ingest_capture(
                        audio_item.modality,
                        audio_item.start_ms,
                        audio_item.end_ms,
                        audio_item.status,
                        audio_item.reason,
                    )
                    continue
                item_started = time.perf_counter()
                start_ms, end_ms, samples = audio_item
                if speech_available:
                    watermark.mark("C", start_ms, end_ms, "done", modality="speech")
                    assert speech_assembler is not None
                    for speech_task in speech_assembler.push(start_ms, samples):
                        submit_speech(speech_task)
                    assert speech_worker is not None
                    speech_worker.drain(publish_speech_result)
                audio_observations = analyze_audio(samples, SAMPLE_RATE, start_ms=start_ms)
                for observation in audio_observations:
                    relation_validator.add_audio(observation)
                audio_deltas = (
                    compare_audio_windows(previous_audio_observations, audio_observations)
                    if previous_audio_observations is not None
                    else []
                )
                sampling_decision = sampling_controller.select_audio(
                    start_ms,
                    audio_observations,
                    signal_changes=audio_deltas,
                )
                if "L0" in levels:
                    publish(_audio_summary(audio_observations, start_ms, end_ms))
                    for observation in audio_deltas:
                        publish(
                            {
                                "record_type": "observation",
                                "level": "L0",
                                "modality": "audio",
                                **observation.to_dict(),
                            }
                        )
                if sampling_decision.selected:
                    dispatch_embedding(
                        bind(
                            provider.encode_audio,
                            samples,
                            interval_ms=(start_ms, end_ms),
                        ),
                        bind(
                            finish_audio_embedding,
                            start_ms=start_ms,
                            end_ms=end_ms,
                            audio_deltas=audio_deltas,
                            signal_delta_score=(
                                sampling_decision.activity_score
                                if sampling_decision.reason == "activity"
                                else None
                            ),
                        ),
                    )
                else:
                    watermark.mark(
                        "E",
                        start_ms,
                        end_ms,
                        "skipped",
                        modality="audio",
                        reason="adaptive_sampling",
                    )
                    mark_window_draft(
                        start_ms,
                        end_ms,
                        modality="audio",
                        l1_status="skipped",
                        l1_reason="adaptive_sampling",
                    )
                    emit_watermark()
                previous_audio_observations = audio_observations
                per_stage_ms["audio_consumer_work"] += (time.perf_counter() - item_started) * 1000
                continue

            video_item = cast(CaptureSpan | _SelectedVideoWork, payload)
            if isinstance(video_item, CaptureSpan):
                mark_ingest_capture(
                    video_item.modality,
                    video_item.start_ms,
                    video_item.end_ms,
                    video_item.status,
                    video_item.reason,
                )
                video_capture_cursor = max(
                    video_capture_cursor,
                    get_capture_cursor("video"),
                )
                continue

            if source_duration_ms is not None and timestamp_ms >= source_duration_ms:
                continue
            item_started = time.perf_counter()
            frame = video_item.frame
            frame_ms = video_item.frame_ms
            if video_item.signal_selected:
                capture_end_ms = frame_ms + 1
                video_capture_cursor = max(
                    video_capture_cursor,
                    capture_cursors["video"],
                    capture_end_ms,
                )
                small_frame = _video_signal_frame(video_item)
                if last_signal is not None:
                    observations = analyze_video_frames(
                        (last_signal, (frame_ms, small_frame)),
                        width=160,
                        height=90,
                    )
                    for observation in observations:
                        relation_validator.add_video(observation)
                        if "L0" in active_levels:
                            publish(
                                {
                                    "record_type": "observation",
                                    "level": "L0",
                                    "modality": "video",
                                    **observation.to_dict(),
                                }
                            )
                        if (
                            observation.subtype == "scene_cut"
                            and observation.value is True
                            and "L0" in active_levels
                        ):
                            if embedding_worker is not None:
                                embedding_worker.wait_idle(apply_embedding_result)

                            def process_scene_cut(
                                observation: SignalObservation = observation,
                            ) -> None:
                                nonlocal emitted_events
                                event = reducer.ingest_signal(
                                    stream_id,
                                    epoch,
                                    observation,
                                    window_id=(
                                        f"scene-cut:{observation.start_ms}:"
                                        f"{observation.end_ms}"
                                    ),
                                )
                                if event is not None:
                                    store.append(event, expected_revision=0)
                                    publish({"record_type": "event", **event.to_dict()})
                                    emitted_events += 1

                            dispatch_l1_work(process_scene_cut)
                last_signal = (frame_ms, small_frame)

            if not video_item.embedding_selected:
                skip_reason = video_item.embedding_skip_reason
                if skip_reason is not None:
                    video_embedding_gap_reason = skip_reason
                    mark_semantic_origin("video", frame_ms)
                    skip_end_ms = frame_ms + 1
                    if skip_reason != "embedding_stride" and skip_end_ms > video_embedding_cursor:
                        watermark.mark_uncovered(
                            "E",
                            video_embedding_cursor,
                            skip_end_ms,
                            "skipped",
                            modality="video",
                            reason=skip_reason,
                        )
                        video_embedding_cursor = skip_end_ms
                        emit_watermark()
                    if skip_reason != "embedding_stride":
                        e_horizon = watermark.snapshot(through_ms=skip_end_ms).E_ms
                        coverage_end_ms = min(skip_end_ms, e_horizon)
                        with video_level_cursor_lock:
                            level_cursor = video_level_cursor
                        if coverage_end_ms > level_cursor:
                            for stage in semantic_coverage_stages:
                                watermark.mark_uncovered(
                                    stage,
                                    level_cursor,
                                    coverage_end_ms,
                                    "skipped",
                                    level="L1",
                                    reason=skip_reason,
                                )
                            with video_level_cursor_lock:
                                video_level_cursor = max(video_level_cursor, coverage_end_ms)
                        emit_watermark()

            if video_item.embedding_selected:
                image = frame.to_ndarray(format="rgb24")
                start_ms = frame_ms
                end_ms = frame_ms + window_ms
                if source_duration_ms is not None:
                    end_ms = min(end_ms, source_duration_ms)
                sample_end_ms = min(end_ms, frame_ms + 1)
                if start_ms > video_embedding_cursor:
                    watermark.mark_uncovered(
                        "E",
                        video_embedding_cursor,
                        start_ms,
                        "skipped",
                        modality="video",
                        reason=video_embedding_gap_reason
                        or (
                            "adaptive_sampling"
                            if sampling_profile == "adaptive"
                            else "embedding_stride"
                        ),
                    )
                video_embedding_gap_reason = None
                video_embedding_cursor = max(video_embedding_cursor, sample_end_ms)
                dispatch_embedding(
                    bind(
                        provider.encode_frame,
                        image,
                        pts_ms=frame_ms,
                        max_soft_tokens=(
                            DEFAULT_IMAGE_SOFT_TOKENS
                            if vision_profile == "standard"
                            else COMPACT_IMAGE_SOFT_TOKENS
                        ),
                    ),
                    bind(
                        finish_video_embedding,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        sample_end_ms=sample_end_ms,
                        signal_delta_score=video_item.sampling_activity_score,
                    ),
                )
            per_stage_ms["video_consumer_work"] += (time.perf_counter() - item_started) * 1000

        observe_runtime_load(force=True)
        if embedding_worker is not None:
            embedding_worker.finish(apply_embedding_result)
            embedding_worker_report = {
                "enabled": True,
                "execution": "serial_background",
                **embedding_worker.snapshot(),
            }
            if shared_embedding_dispatcher is not None:
                embedding_worker_report["shared_dispatcher"] = (
                    shared_embedding_dispatcher.snapshot()
                )
        if l1_worker is not None:
            l1_worker.finish()
            l1_worker_report = {
                "enabled": True,
                "execution": "serial_background",
                **l1_worker.snapshot(),
            }
        # Let the load controller observe drained inference before post-pass L2 admission.
        observe_runtime_load(force=True)

        per_stage_ms["shared_media_interleave"] = (
            time.perf_counter() - shared_consumer_started
        ) * 1000
        if speech_assembler is not None:
            final_task = speech_assembler.flush()
            if final_task is not None:
                submit_speech(final_task)
        if speech_worker is not None:
            speech_worker.drain(publish_speech_result)

        if video_prefetch is not None:
            video_prefetch.close()
        if shared_prefetch is not None:
            shared_prefetch.close()
        if "video" in media.available_modalities:
            video_capture_cursor = max(video_capture_cursor, get_capture_cursor("video"))
            embedding_horizon = source_duration_ms or video_capture_cursor
            if video_embedding_cursor < embedding_horizon:
                watermark.mark_uncovered(
                    "E",
                    video_embedding_cursor,
                    embedding_horizon,
                    "skipped",
                    modality="video",
                    reason=video_embedding_gap_reason
                    or (
                        "adaptive_sampling"
                        if sampling_profile == "adaptive"
                        else "embedding_stride"
                    ),
                )

        if speech_worker is not None:
            for attempt in range(3):
                if not deferred_speech_tasks:
                    break
                speech_worker.drain(publish_speech_result)
                observe_runtime_load(force=True)
                flush_deferred_speech()
                if deferred_speech_tasks and attempt < 2:
                    time.sleep(0.25)
            while deferred_speech_tasks:
                task = deferred_speech_tasks.popleft()
                decision = load_controller.admit(WorkPriority.L2_ASR)
                reason: str | None = decision.reason or "asr_queue_full"
                speech_admission_drop_count += 1
                publish_speech_result(
                    SpeechResult(task.start_ms, task.end_ms, None, "dropped", reason)
                )
            speech_worker.finish(publish_speech_result)
            speech_worker_report = {
                "enabled": True,
                "admission_dropped": speech_admission_drop_count,
                **speech_worker.snapshot(),
            }
            # Each window result is a partial transcript of the whole source.
            # Promote successful windows only after all source media has been read.
            if stop_event is None or not stop_event.is_set():
                for partial in store.speech_segments(stream_id, epoch):
                    if partial.get("status") != "partial":
                        continue
                    final = dict(partial)
                    revision = cast(int, partial["revision"])
                    final.update(
                        {
                            "revision": revision + 1,
                            "supersedes_revision": revision,
                            "status": "final",
                            "source_complete": True,
                        }
                    )
                    store.append_speech_segment(stream_id, epoch, final)
                    publish(final)
            per_stage_ms["speech_asr_worker"] = (time.perf_counter() - speech_started) * 1000

        assessment = relation_validator.assess(available_modalities=set(media.available_modalities))
        relation_assessment = assessment.to_dict()
        publish(
            {
                "record_type": "cross_modal_relation",
                "schema_version": 1,
                "stream_id": stream_id,
                "epoch": epoch,
                **relation_assessment,
            }
        )
        for match in assessment.matches:
            event_id = uuid4().hex
            event = TimelineEvent(
                stream_id=stream_id,
                epoch=epoch,
                event_id=event_id,
                revision=1,
                start_ms=match.start_ms,
                end_ms=match.end_ms,
                kind="cross_modal_coincidence",
                level="L1",
                state="committed",
                modality_mask={"audio": True, "video": True, "speech": False},
                claims=(
                    TimelineClaim(
                        claim_id=f"claim-{event_id}",
                        label="temporally_coincident",
                        text_ru=(
                            "Смена кадра совпадает по времени с обнаруженным звуковым "
                            "началом; причинная связь не установлена."
                        ),
                        decision="accepted",
                        raw_cosine=None,
                        margin=None,
                        evidence_refs=(
                            (
                                f"audio:onset:{match.audio_onset.start_ms}-"
                                f"{match.audio_onset.end_ms}:"
                                f"{match.audio_onset.method_version}"
                            ),
                            (
                                f"video:scene_cut:{match.scene_cut.start_ms}-"
                                f"{match.scene_cut.end_ms}:"
                                f"{match.scene_cut.method_version}"
                            ),
                        ),
                        window_ids=(
                            f"audio-onset:{match.audio_onset.start_ms}-{match.audio_onset.end_ms}",
                            f"video-cut:{match.scene_cut.start_ms}-{match.scene_cut.end_ms}",
                        ),
                        model_revision="cross-modal-pts-v1",
                        sample_count=1,
                    ),
                ),
            )
            store.append(event, expected_revision=0)
            publish({"record_type": "event", **event.to_dict()})
            emitted_events += 1

        # A completed finite file gives L1 events a final, committed source
        # revision before L2 and L3 consume them.
        if "L1" in active_levels:
            for event in sorted(
                (item for item in latest_events.values() if item.level == "L1"),
                key=lambda item: (item.start_ms, item.end_ms, item.event_id),
            ):
                if event.state != "committed":
                    committed = replace(
                        event,
                        revision=event.revision + 1,
                        state="committed",
                        supersedes_revision=event.revision,
                        updated_at_utc=datetime.now(UTC).isoformat(),
                    )
                    store.append(committed, expected_revision=event.revision)
                    publish({"record_type": "event", **committed.to_dict()})
                    emitted_events += 1

        state_reducer = TemporalStateReducer(min_repeats=2)
        state_started = time.perf_counter()
        refined_events: list[TimelineEvent] = []
        host_sample, current_host_metrics_available = _host_load_sample()
        host_metrics_available = (
            host_metrics_available
            or current_host_metrics_available
            or ingest_telemetry.host_metrics_available
        )
        pending_prefetch = [
            telemetry
            for telemetry in prefetch_telemetry.values()
            if telemetry.current_depth > 0
        ]
        pressure_sample = host_sample
        if pending_prefetch:
            most_loaded_queue = max(
                pending_prefetch,
                key=lambda item: item.current_depth / item.capacity,
            )
            pressure_sample = LoadSample(
                queue_depth=most_loaded_queue.current_depth,
                queue_capacity=most_loaded_queue.capacity,
                source_lag_ms=host_sample.source_lag_ms,
                cpu_percent=host_sample.cpu_percent,
                rss_bytes=host_sample.rss_bytes,
                memory_limit_bytes=host_sample.memory_limit_bytes,
            )
        load_controller.observe(pressure_sample, source_id=load_source_id)
        scheduler_report: dict[str, object] = {
            "queues": {},
            "load": load_controller.status.to_dict(),
            "backpressure_count": 0,
            "pressure_rejected_count": 0,
            "cancelled_count": 0,
            "failed_count": 0,
        }
        l2_skipped_events: list[TimelineEvent] = []
        live_level_report: dict[str, object] | None = None
        if progressive_workers is not None:
            with live_coverage_lock:
                remaining_coverage = tuple(live_pending_coverage)
                live_pending_coverage.clear()
            progressive_workers.submit_coverage(remaining_coverage, block=True)
            progressive_workers.finish()
            live_level_report = progressive_workers.snapshot()
            scheduler_report = {
                **live_level_report,
                "load": load_controller.status.to_dict(),
            }
            live_current_events = store.current_events(stream_id, epoch)
            refined_events = [event for event in live_current_events if event.level == "L2"]
            l2_report = cast(dict[str, Any], live_level_report.get("l2", {}))
            emitted_events += int(l2_report.get("completed", 0))
            per_stage_ms["l2_state_refinement"] = sum(
                cast(list[float], l2_report.get("latency_ms_samples", []))
            )
        elif "L2" in active_levels:
            state_deltas: dict[str, dict[str, Any]] = {}
            scheduler_errors: list[dict[str, str]] = []
            backpressure_events: list[dict[str, str]] = []

            async def unused_processor(_job: ScheduledJob) -> TimelineEvent:
                raise RuntimeError("this analyzer pass submits L2 jobs only")

            async def process_l2(job: ScheduledJob) -> TimelineEvent:
                source_event = job.payload
                if not isinstance(source_event, TimelineEvent):
                    raise TypeError("L2 scheduler payload must be a TimelineEvent")
                delta = state_reducer.ingest(source_event)
                if delta is not None:
                    state_deltas[source_event.event_id] = delta.to_dict()
                return replace(
                    source_event,
                    revision=source_event.revision + 1,
                    level="L2",
                    state=("refined" if delta is not None and delta.published else "committed"),
                    supersedes_revision=source_event.revision,
                    updated_at_utc=datetime.now(UTC).isoformat(),
                )

            def on_scheduler_error(job: ScheduledJob, error: Exception) -> None:
                source_event = job.payload
                if isinstance(source_event, TimelineEvent):
                    l2_skipped_events.append(source_event)
                scheduler_errors.append(
                    {
                        "event_id": job.key.event_id,
                        "error": f"{type(error).__name__}: {error}"[:500],
                    }
                )

            def on_scheduler_backpressure(job: ScheduledJob, reason: str) -> None:
                source_event = job.payload
                if isinstance(source_event, TimelineEvent):
                    l2_skipped_events.append(source_event)
                backpressure_events.append({"event_id": job.key.event_id, "reason": reason})

            scheduler = AsyncLevelScheduler(
                processors={
                    "L1": unused_processor,
                    "L2": process_l2,
                    "L3": unused_processor,
                },
                writer=store,
                queue_capacity=64,
                on_error=on_scheduler_error,
                on_backpressure=on_scheduler_backpressure,
                load_controller=load_controller,
                load_source_id=load_source_id,
            )

            async def schedule_refinements() -> None:
                scheduler.start()
                try:
                    scheduler.observe_load(
                        source_lag_ms=pressure_sample.source_lag_ms,
                        cpu_percent=pressure_sample.cpu_percent,
                        rss_bytes=pressure_sample.rss_bytes,
                        memory_limit_bytes=pressure_sample.memory_limit_bytes,
                    )
                    events_to_refine = sorted(
                        latest_events.values(),
                        key=lambda item: (item.start_ms, item.end_ms, item.event_id),
                    )
                    for event in events_to_refine:
                        job = ScheduledJob(
                            key=JobKey(
                                stream_id=event.stream_id,
                                epoch=event.epoch,
                                event_id=event.event_id,
                                revision=event.revision + 1,
                                level="L2",
                            ),
                            expected_revision=event.revision,
                            payload=event,
                        )
                        while True:
                            result = scheduler.submit(job)
                            if result is SubmitResult.FULL:
                                await scheduler.wait_idle()
                                continue
                            if result is SubmitResult.PRESSURE:
                                break
                            break
                    await scheduler.wait_idle()
                finally:
                    await scheduler.close()

            asyncio.run(schedule_refinements())
            scheduler_report = scheduler.snapshot()
            current_events = {
                event.event_id: event for event in store.current_events(stream_id, epoch)
            }
            for source_event in sorted(
                latest_events.values(),
                key=lambda item: (item.start_ms, item.end_ms, item.event_id),
            ):
                delta = state_deltas.get(source_event.event_id)
                if delta is not None:
                    publish(
                        {
                            "record_type": "state_delta",
                            "level": "L2",
                            "source_event_id": source_event.event_id,
                            "source_revision": source_event.revision,
                            **delta,
                        }
                    )
                refined = current_events.get(source_event.event_id)
                if refined is None or refined.level != "L2":
                    if source_event not in l2_skipped_events:
                        l2_skipped_events.append(source_event)
                    continue
                publish({"record_type": "event", **refined.to_dict()})
                refined_events.append(refined)
                emitted_events += 1
            latest_events.update({event.event_id: event for event in refined_events})
            if backpressure_events or scheduler_errors:
                publish(
                    {
                        "record_type": "scheduler_degradation",
                        "level": "L2",
                        "backpressure": backpressure_events[:100],
                        "errors": scheduler_errors[:100],
                        "sample_limit": 100,
                        "load": load_controller.status.to_dict(),
                    }
                )
        if progressive_workers is None:
            per_stage_ms["l2_state_refinement"] = (time.perf_counter() - state_started) * 1000

        l3_allowed = False
        if progressive_workers is not None:
            l3_allowed = "L3" in active_levels
        elif "L3" in active_levels:
            latest_host_sample, latest_host_metrics_available = _host_load_sample()
            host_metrics_available = host_metrics_available or latest_host_metrics_available
            load_controller.observe(latest_host_sample, source_id=load_source_id)
            l3_allowed = load_controller.admit(WorkPriority.L3_NARRATION).admitted
        if progressive_workers is None and "L3" in active_levels and not l3_allowed:
            publish(
                {
                    "record_type": "scheduler_degradation",
                    "level": "L3",
                    "reason": f"load_{load_controller.status.mode.value}",
                    "load": load_controller.status.to_dict(),
                }
            )

        # Turn the processed sparse intervals into visible coverage on every
        # semantic level, including deliberate skips and decode holes.
        merged_intervals: list[tuple[int, int]] = []
        for start_ms, end_ms in sorted(processed_intervals):
            if merged_intervals and start_ms <= merged_intervals[-1][1]:
                merged_intervals[-1] = (
                    merged_intervals[-1][0],
                    max(merged_intervals[-1][1], end_ms),
                )
            else:
                merged_intervals.append((start_ms, end_ms))
        for start_ms, end_ms in merged_intervals:
            for level in ("L1", "L2", "L3"):
                if level == "L1":
                    # L1 commits per completed window while the source is live.
                    # Terminal gap filling below closes any unprocessed spans.
                    continue
                elif progressive_workers is not None:
                    # Online L2/L3 workers emit revisioned watermarks at their
                    # queued coverage barriers while the source is arriving.
                    continue
                elif level == "L2":
                    interval_skipped = any(
                        event.start_ms < end_ms and event.end_ms > start_ms
                        for event in l2_skipped_events
                    )
                    status: CoverageStatus = (
                        "done" if level in active_levels and not interval_skipped else "skipped"
                    )
                    reason = (
                        None
                        if status == "done"
                        else "runtime_backpressure"
                        if interval_skipped
                        else "level_not_requested"
                    )
                    watermark.mark_revisioned(
                        "D", start_ms, end_ms, status, level=level, reason=reason
                    )
                    watermark.mark_revisioned(
                        "R", start_ms, end_ms, status, level=level, reason=reason
                    )
                else:
                    status = "done" if l3_allowed else "skipped"
                    reason = (
                        None
                        if status == "done"
                        else "runtime_backpressure"
                        if level in active_levels
                        else "level_not_requested"
                    )
                    watermark.mark_revisioned(
                        "D", start_ms, end_ms, status, level=level, reason=reason
                    )
                    if status == "skipped":
                        watermark.mark_revisioned(
                            "R", start_ms, end_ms, status, level=level, reason=reason
                        )

        narration_started = time.perf_counter()
        narration_errors: list[tuple[int, int, str]] = []
        narration_ranges: list[tuple[int, int]] = []
        narration_latency_ms_samples: list[float] = []
        narration_generation_rate_samples: list[float] = []
        narration_backend_counts = {"qwen": 0, "template": 0}
        narration_fallback_count = 0
        narration_unsupported_claim_count = 0
        narration_generated_tokens = 0
        narration_generation_ms = 0.0
        narration_measured_generations = 0
        if live_level_report is not None:
            narration_report = cast(dict[str, Any], live_level_report.get("narration", {}))
            narration_errors = cast(
                list[tuple[int, int, str]], narration_report.get("errors", [])
            )
            narration_ranges = cast(
                list[tuple[int, int]], narration_report.get("ranges", [])
            )
            narration_latency_ms_samples = cast(
                list[float], narration_report.get("latency_ms_samples", [])
            )
            narration_backend_counts = cast(
                dict[str, int], narration_report.get("backend_counts", narration_backend_counts)
            )
            narration_fallback_count = int(narration_report.get("fallback_count", 0))
            narration_unsupported_claim_count = int(
                narration_report.get("unsupported_claim_count", 0)
            )
            narration_generated_tokens = int(narration_report.get("generated_tokens") or 0)
            narration_generation_ms = float(narration_report.get("generation_ms") or 0.0)
            narration_measured_generations = len(narration_latency_ms_samples)
            per_stage_ms["l3_narration"] = sum(
                cast(
                    list[float],
                    cast(dict[str, Any], live_level_report.get("l3", {})).get(
                        "latency_ms_samples", []
                    ),
                )
            )
            tokens_per_second = narration_report.get("tokens_per_second")
            if isinstance(tokens_per_second, (int, float)):
                narration_generation_rate_samples.append(float(tokens_per_second))
        if l3_allowed and live_level_report is None:
            l2_events = [event for event in latest_events.values() if event.level == "L2"]
            requests = _narration_batches(l2_events, stream_id=stream_id, epoch=epoch)
            if not requests:
                publish(
                    {
                        "record_type": "narration_skipped",
                        "level": "L3",
                        "reason": "no_accepted_claims_with_display_text",
                    }
                )
            else:
                try:
                    from shsd.captions.narrator import QwenNarrator, TemplateNarrator

                    narrator: QwenNarrator | TemplateNarrator
                    if narrator_mode == "template":
                        narrator = TemplateNarrator()
                    else:
                        lock_path = Path(__file__).resolve().parents[2] / "models.lock.json"
                        qwen_model = json.loads(lock_path.read_text(encoding="utf-8"))["models"][
                            "qwen3_0_6b"
                        ]
                        narrator = QwenNarrator(
                            qwen_model,
                            models_dir,
                            Path(__file__).resolve().parents[2],
                            threads=threads,
                            max_tokens=96,
                        )
                except Exception as error:
                    for request in requests:
                        narration_errors.append((*request.time_range, str(error)))
                        publish(
                            {
                                "record_type": "narration_error",
                                "level": "L3",
                                "time_range": {
                                    "start_ms": request.time_range[0],
                                    "end_ms": request.time_range[1],
                                },
                                "error": str(error)[:500],
                                "event_revisions": [
                                    {"event_id": item.event_id, "revision": item.revision}
                                    for item in request.event_refs
                                ],
                            }
                        )
                else:
                    for request in requests:
                        try:
                            result = narrator.narrate(request)
                        except Exception as error:
                            narration_errors.append((*request.time_range, str(error)))
                            publish(
                                {
                                    "record_type": "narration_error",
                                    "level": "L3",
                                    "time_range": {
                                        "start_ms": request.time_range[0],
                                        "end_ms": request.time_range[1],
                                    },
                                    "error": str(error)[:500],
                                    "event_revisions": [
                                        {"event_id": item.event_id, "revision": item.revision}
                                        for item in request.event_refs
                                    ],
                                }
                            )
                            continue
                        publish(result.to_dict())
                        narration_latency_ms_samples.append(float(result.latency_ms))
                        narration_backend_counts[result.backend] += 1
                        narration_fallback_count += result.status == "fallback"
                        narration_unsupported_claim_count += len(
                            result.response.new_unsupported_claims
                        )
                        if result.generation_tokens_per_second is not None:
                            narration_generation_rate_samples.append(
                                float(result.generation_tokens_per_second)
                            )
                        if (
                            result.generated_token_count is not None
                            and result.generation_ms is not None
                        ):
                            narration_generated_tokens += result.generated_token_count
                            narration_generation_ms += float(result.generation_ms)
                            narration_measured_generations += 1
                        narration_ranges.append((result.response.start_ms, result.response.end_ms))
            for start_ms, end_ms in merged_intervals:
                boundaries = {start_ms, end_ms}
                for left, right in narration_ranges:
                    if left < end_ms and right > start_ms:
                        boundaries.update((max(start_ms, left), min(end_ms, right)))
                for left, right, _ in narration_errors:
                    if left < end_ms and right > start_ms:
                        boundaries.update((max(start_ms, left), min(end_ms, right)))
                ordered = sorted(boundaries)
                for segment_start, segment_end in zip(ordered, ordered[1:], strict=False):
                    failed = any(
                        error_start <= segment_start and error_end >= segment_end
                        for error_start, error_end, _ in narration_errors
                    )
                    succeeded = any(
                        success_start <= segment_start and success_end >= segment_end
                        for success_start, success_end in narration_ranges
                    )
                    narration_status: CoverageStatus = (
                        "failed" if failed else "done" if succeeded else "skipped"
                    )
                    narration_reason = (
                        None
                        if narration_status == "done"
                        else (
                            "narration_failed"
                            if narration_status == "failed"
                            else "no_supported_claim_in_interval"
                        )
                    )
                    watermark.mark(
                        "R",
                        segment_start,
                        segment_end,
                        narration_status,
                        level="L3",
                        reason=narration_reason,
                    )
        if live_level_report is None:
            per_stage_ms["l3_narration"] = (time.perf_counter() - narration_started) * 1000

        # Close the known media horizon. Uncovered regions are explicit gaps;
        # unavailable tracks already carry their terminal unavailable status.
        coverage_end_ms = source_duration_ms or max(capture_cursors.values(), default=0)
        media_stages: tuple[CoverageStage, ...] = ("C", "E")
        for modality in ("audio", "video"):
            if modality not in media.unavailable_modalities:
                for stage in media_stages:
                    _fill_coverage_gaps(
                        watermark,
                        stage,
                        coverage_end_ms,
                        modality=modality,
                        reason=(
                            "not_observed_by_decoder" if stage == "C" else "no_embedding_coverage"
                        ),
                    )
        if speech_available:
            speech_stages: tuple[CoverageStage, ...] = ("C", "E")
            for stage in speech_stages:
                _fill_coverage_gaps(
                    watermark,
                    stage,
                    coverage_end_ms,
                    modality="speech",
                    reason="asr_not_processed",
                )
        coverage_levels: tuple[Level, ...] = ("L1", "L2", "L3")
        coverage_stages: tuple[CoverageStage, ...] = ("D", "R")
        for level in coverage_levels:
            for stage in coverage_stages:
                _fill_coverage_gaps(
                    watermark,
                    stage,
                    coverage_end_ms,
                    level=level,
                    reason="level_not_requested" if level not in active_levels else "not_processed",
                )
        emit_watermark(coverage_end_ms, advance_source_horizon=True)

    elapsed_s = time.perf_counter() - started
    resource_sampler = _ACTIVE_RESOURCE_SAMPLER.get()
    metrics = {
        "record_type": "metrics",
        "end_to_end_elapsed": round(elapsed_s, 6),
        "end_to_end_elapsed_unit": "seconds",
        "profile_candidate_embedding_ms": round(profile_embedding_ms, 3),
        "stage_timings_ms": {
            "embedding_model_and_text_profiles": round(profile_embedding_ms, 3),
            **{key: round(value, 3) for key, value in per_stage_ms.items()},
        },
        "worker_stage_timings": [
            {
                "worker": "cpu-main",
                "device": "cpu",
                "threads": threads,
                "stages_ms": {
                    "embedding_model_and_text_profiles": round(profile_embedding_ms, 3),
                    **{key: round(value, 3) for key, value in per_stage_ms.items()},
                },
            }
        ],
        "window_match_count": emitted_matches,
        "skipped_match_count": skipped_matches,
        "event_revision_count": emitted_events,
        "caption_count": len(narration_ranges),
        "narration_error_count": len(narration_errors),
        "narration_backend_counts": narration_backend_counts,
        "narration_fallback_count": narration_fallback_count,
        "narration_unsupported_claim_count": narration_unsupported_claim_count,
        "narration_latency_ms_samples": narration_latency_ms_samples,
        "narration_token_throughput": {
            "generated_tokens": narration_generated_tokens
            if narration_generation_ms > 0
            else None,
            "generation_ms": round(narration_generation_ms, 3)
            if narration_generation_ms > 0
            else None,
            "tokens_per_second": round(
                narration_generated_tokens / (narration_generation_ms / 1000), 3
            )
            if narration_generation_ms > 0
            else round(
                sum(narration_generation_rate_samples)
                / len(narration_generation_rate_samples),
                3,
            )
            if narration_generation_rate_samples
            else None,
            "measured_generations": len(narration_generation_rate_samples)
            or narration_measured_generations,
            "caption_count": len(narration_ranges),
            "fallback_count": narration_fallback_count,
        },
        "speech_segment_count": speech_result_count,
        "speech_error_count": speech_error_count,
        "speech_dropped_count": speech_dropped_count,
        "speech_worker": speech_worker_report,
        "host_load": {
            "metrics_available": host_metrics_available,
            "runtime_observation_count": runtime_load_observation_count,
            **load_controller.status.to_dict(),
        },
        "process_resources": (
            resource_sampler.snapshot()
            if resource_sampler is not None
            else {
                "available": False,
                "current_process_tree_rss_bytes": 0,
                "peak_process_tree_rss_bytes": 0,
                "peak_process_count": 0,
                "system_cpu_percent": 0.0,
                "sample_interval_ms": 0,
            }
        ),
        "media_ingest": ingest_telemetry.to_dict(load=load_controller.status.to_dict()),
        "source_sessions": {
            "metadata_inspection": 1,
            "duration_inspection": 0 if remote_source else 1,
            "decoder_demux": ingest_telemetry.decoder_sessions,
            "total": 1
            + (0 if remote_source else 1)
            + ingest_telemetry.decoder_sessions,
        },
        "prefetch": {
            modality: telemetry.to_dict() for modality, telemetry in prefetch_telemetry.items()
        },
        "media_admission": media_admission_telemetry.to_dict(),
        "semantic_scheduler": scheduler_report,
        "embedding_worker": embedding_worker_report,
        "l1_worker": l1_worker_report,
        "sampling": sampling_controller.snapshot(),
        "cross_modal_relations": relation_assessment,
        "final_watermarks": watermark.snapshot(through_ms=coverage_end_ms).to_dict(),
    }
    publish(metrics)
    return metrics


def encode_jsonl(record: dict[str, Any]) -> str:
    """Serialize one JSONL record with stable keys and no non-finite numbers."""
    return json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False)
