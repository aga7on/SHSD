"""Decode local media only after its compressed packets pass through MediaRing."""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from threading import Event
from typing import Any, Literal, cast

import av

from shsd.ingest.clock import pts_to_ms
from shsd.ingest.demux import Modality, open_media_container
from shsd.ingest.live import (
    LiveSourceInterruptedError,
    is_rtsp_source,
    raise_live_source_error,
)
from shsd.ingest.ring import (
    RING_MAX_CHUNKS,
    RING_MEMORY_BYTES,
    RING_SPILL_BYTES,
    RING_WINDOW_MS,
    DroppedChunk,
    MediaRing,
    default_spill_directory,
)
from shsd.workers.scheduler import LoadSample, RuntimeLoadController


@dataclass(frozen=True, slots=True)
class CaptureSpan:
    """One capture interval, passed to the consumer thread for watermarking."""

    modality: Modality
    start_ms: int
    end_ms: int
    status: Literal["done", "dropped"]
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DecodedFrame:
    """A decoded frame, distinct from capture updates in the prefetch stream."""

    frame: Any


@dataclass(slots=True)
class RingDecodeTelemetry:
    """Bounded aggregate evidence for compressed-packet ingestion and decode."""

    packets_by_modality: dict[Modality, int] = field(
        default_factory=lambda: {"audio": 0, "video": 0}
    )
    dropped_by_modality: dict[Modality, int] = field(
        default_factory=lambda: {"audio": 0, "video": 0}
    )
    dropped_bytes: int = 0
    peak_buffer_bytes: int = 0
    peak_memory_bytes: int = 0
    peak_spill_bytes: int = 0
    peak_rss_bytes: int = 0
    peak_cpu_percent: float = 0.0
    host_metrics_available: bool = False
    decoder_sessions: int = 0

    @property
    def packet_count(self) -> int:
        return sum(self.packets_by_modality.values())

    @property
    def dropped_count(self) -> int:
        return sum(self.dropped_by_modality.values())

    def to_dict(self, *, load: dict[str, object]) -> dict[str, object]:
        return {
            "packets": self.packet_count,
            "decoder_sessions": self.decoder_sessions,
            "packets_by_modality": dict(self.packets_by_modality),
            "dropped_count": self.dropped_count,
            "dropped_by_modality": dict(self.dropped_by_modality),
            "dropped_bytes": self.dropped_bytes,
            "ring": {
                "window_ms": RING_WINDOW_MS,
                "max_chunks": RING_MAX_CHUNKS,
                "memory_capacity_bytes": RING_MEMORY_BYTES,
                "spill_capacity_bytes": RING_SPILL_BYTES,
                "peak_buffer_bytes": self.peak_buffer_bytes,
                "peak_memory_bytes": self.peak_memory_bytes,
                "peak_spill_bytes": self.peak_spill_bytes,
            },
            "host": {
                "metrics_available": self.host_metrics_available,
                "peak_cpu_percent": round(self.peak_cpu_percent, 2),
                "peak_rss_bytes": self.peak_rss_bytes,
                "load": load,
            },
        }


class _CaptureSpanBoundaryTracker:
    """Infer packet coverage end from the next PTS when duration is absent."""

    def __init__(self) -> None:
        self._pending: dict[Modality, CaptureSpan] = {}

    def push(
        self,
        modality: Modality,
        start_ms: int,
        end_ms: int,
        status: Literal["done", "dropped"],
        reason: str | None,
        *,
        duration_known: bool,
    ) -> tuple[CaptureSpan, ...]:
        result: list[CaptureSpan] = []
        previous = self._pending.pop(modality, None)
        if previous is not None:
            inferred_end = max(previous.end_ms, start_ms, previous.start_ms + 1)
            result.append(
                CaptureSpan(
                    modality,
                    previous.start_ms,
                    inferred_end,
                    previous.status,
                    previous.reason,
                )
            )
        current = CaptureSpan(modality, start_ms, end_ms, status, reason)
        if duration_known:
            result.append(current)
        else:
            self._pending[modality] = current
        return tuple(result)

    def finish(self) -> tuple[CaptureSpan, ...]:
        result = tuple(self._pending.values())
        self._pending.clear()
        return result


def _memory_limit_bytes() -> int:
    try:
        return max(0, int(os.environ.get("SHSD_MEMORY_LIMIT_BYTES", "0")))
    except ValueError:
        return 0


def _iter_source_packets(
    container: Any,
    streams: list[Any],
    source: str | Path,
    *,
    stop_event: Event | None = None,
) -> Generator[Any, None, None]:
    """Yield packets, treating read errors during an explicit stop as graceful EOF."""
    try:
        yield from container.demux(*streams)
    except (av.error.FFmpegError, OSError) as error:
        if stop_event is not None and stop_event.is_set():
            return
        raise_live_source_error(source, error)


def _decode_or_stop(
    codec_context: Any, packet: Any, stop_event: Event | None
) -> list[Any]:
    """Ignore decoder shutdown errors only after an explicit live stop."""
    try:
        return cast(list[Any], codec_context.decode(packet))
    except Exception:
        if stop_event is not None and stop_event.is_set():
            return []
        raise


def iter_decoded_frames_from_ring(
    source: str | Path,
    *,
    stream_id: str,
    modality: Modality,
    telemetry: RingDecodeTelemetry,
    load_controller: RuntimeLoadController,
    stop_event: Event | None = None,
) -> Generator[CaptureSpan | DecodedFrame, None, None]:
    """Decode one modality from ring lease bytes."""
    yield from cast(
        Generator[CaptureSpan | DecodedFrame, None, None],
        _iter_decoded_from_ring(
            source,
            stream_id=stream_id,
            modalities=(modality,),
            telemetry=telemetry,
            load_controller=load_controller,
            stop_event=stop_event,
            tagged=False,
        ),
    )


def iter_decoded_media_from_ring(
    source: str | Path,
    *,
    stream_id: str,
    modalities: tuple[Modality, ...],
    telemetry: RingDecodeTelemetry,
    load_controller: RuntimeLoadController,
    stop_event: Event | None = None,
) -> Generator[tuple[Modality, CaptureSpan | DecodedFrame], None, None]:
    """Open a source once and decode its available audio/video tracks together."""
    yield from cast(
        Generator[tuple[Modality, CaptureSpan | DecodedFrame], None, None],
        _iter_decoded_from_ring(
            source,
            stream_id=stream_id,
            modalities=modalities,
            telemetry=telemetry,
            load_controller=load_controller,
            stop_event=stop_event,
            tagged=True,
        ),
    )


def _iter_decoded_from_ring(
    source: str | Path,
    *,
    stream_id: str,
    modalities: tuple[Modality, ...],
    telemetry: RingDecodeTelemetry,
    load_controller: RuntimeLoadController,
    stop_event: Event | None,
    tagged: bool,
) -> Generator[
    CaptureSpan | DecodedFrame | tuple[Modality, CaptureSpan | DecodedFrame], None, None
]:
    """Yield capture spans and decoded frames from one or more selected tracks.

    When both tracks are requested, a shared ring and one PyAV demux session
    preserve source interleave. Ring overflow emits an explicit dropped span.
    """
    if not modalities:
        return
    ring = MediaRing(
        window_ms=RING_WINDOW_MS,
        max_memory_bytes=RING_MEMORY_BYTES,
        max_chunks=RING_MAX_CHUNKS,
        spill_dir=default_spill_directory(),
        max_spill_bytes=RING_SPILL_BYTES,
    )
    process: Any = None
    psutil_module: Any = None
    host_available = False
    last_sample = time.monotonic()
    last_cpu = 0.0
    last_rss = 0
    capture_boundaries = _CaptureSpanBoundaryTracker()
    try:
        try:
            import psutil

            psutil_module = psutil
            process = psutil_module.Process()
            psutil_module.cpu_percent(interval=None)
            host_available = True
            telemetry.host_metrics_available = True
        except (ImportError, OSError):
            process = None
            psutil_module = None

        # A read timeout lets an API stop or reconnect policy escape a stalled source.
        container_context = open_media_container(source)
        with container_context as container:
            telemetry.decoder_sessions += 1
            streams = [
                candidates[0]
                for modality in modalities
                if (candidates := getattr(container.streams, modality))
            ]
            if not streams:
                return
            fallback_end_ms = {cast(Modality, stream.type): 0 for stream in streams}

            def sample_load(*, force: bool = False) -> None:
                nonlocal host_available, last_cpu, last_rss, last_sample, process, psutil_module
                now = time.monotonic()
                if not force and now - last_sample < 0.25:
                    return
                if process is not None and psutil_module is not None:
                    try:
                        last_cpu = min(
                            100.0,
                            max(0.0, float(psutil_module.cpu_percent(interval=None))),
                        )
                        last_rss = int(process.memory_info().rss)
                        telemetry.peak_cpu_percent = max(
                            telemetry.peak_cpu_percent, last_cpu
                        )
                        telemetry.peak_rss_bytes = max(
                            telemetry.peak_rss_bytes, last_rss
                        )
                    except Exception:
                        process = None
                        psutil_module = None
                        host_available = False
                        telemetry.host_metrics_available = False
                stats = ring.stats
                buffer_bytes = stats.memory_bytes + stats.spill_bytes
                capacity_bytes = RING_MEMORY_BYTES + RING_SPILL_BYTES
                telemetry.peak_buffer_bytes = max(telemetry.peak_buffer_bytes, buffer_bytes)
                telemetry.peak_memory_bytes = max(
                    telemetry.peak_memory_bytes, stats.memory_bytes
                )
                telemetry.peak_spill_bytes = max(
                    telemetry.peak_spill_bytes, stats.spill_bytes
                )
                load_controller.observe(
                    LoadSample(
                        queue_depth=buffer_bytes,
                        queue_capacity=capacity_bytes,
                        cpu_percent=last_cpu,
                        rss_bytes=last_rss,
                        memory_limit_bytes=_memory_limit_bytes(),
                    )
                )
                last_sample = now

            for source_packet in _iter_source_packets(
                container, streams, source, stop_event=stop_event
            ):
                if stop_event is not None and stop_event.is_set():
                    for capture in capture_boundaries.finish():
                        yield (capture.modality, capture) if tagged else capture
                    return
                if source_packet.size <= 0:
                    continue
                modality = cast(Modality, source_packet.stream.type)
                stream = source_packet.stream
                raw_time_base = source_packet.time_base or stream.time_base
                if raw_time_base is None:
                    raise ValueError(f"stream {stream.index} has no usable time_base")
                time_base = Fraction(
                    int(raw_time_base.numerator), int(raw_time_base.denominator)
                )
                timestamp_pts = (
                    source_packet.pts
                    if source_packet.pts is not None
                    else source_packet.dts
                )
                if timestamp_pts is None:
                    start_ms = fallback_end_ms[modality]
                else:
                    start_ms = pts_to_ms(timestamp_pts, time_base)
                duration_pts = (
                    source_packet.duration
                    if source_packet.duration is not None and source_packet.duration > 0
                    else None
                )
                end_ms = (
                    pts_to_ms(timestamp_pts + duration_pts, time_base)
                    if timestamp_pts is not None and duration_pts is not None
                    else start_ms + 1
                )
                end_ms = max(start_ms, end_ms)
                fallback_end_ms[modality] = max(fallback_end_ms[modality], end_ms)
                telemetry.packets_by_modality[modality] += 1
                stored = ring.append(
                    stream_id=stream_id,
                    epoch=0,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    kind=modality,
                    data=bytes(source_packet),
                    source_pts_range=(
                        (source_packet.pts, source_packet.pts + duration_pts)
                        if source_packet.pts is not None and duration_pts is not None
                        else None
                    ),
                )
                coverage_start = max(0, start_ms)
                coverage_end = max(coverage_start + 1, end_ms)
                capture_spans = capture_boundaries.push(
                    modality,
                    coverage_start,
                    coverage_end,
                    "dropped" if isinstance(stored, DroppedChunk) else "done",
                    f"ring_{stored.reason}" if isinstance(stored, DroppedChunk) else None,
                    duration_known=coverage_end > coverage_start + 1,
                )
                for capture in capture_spans:
                    yield (modality, capture) if tagged else capture
                if isinstance(stored, DroppedChunk):
                    telemetry.dropped_by_modality[modality] += 1
                    telemetry.dropped_bytes += stored.size_bytes
                    sample_load()
                    continue

                with ring.lease(stored.chunk_id) as lease:
                    decoded_packet = av.Packet(lease.read())
                    decoded_packet.stream = stream
                    decoded_packet.pts = source_packet.pts
                    decoded_packet.dts = source_packet.dts
                    decoded_packet.duration = source_packet.duration
                    decoded_packet.time_base = time_base
                    frames = _decode_or_stop(stream.codec_context, decoded_packet, stop_event)
                sample_load()
                for frame in frames:
                    decoded = DecodedFrame(frame)
                    yield (modality, decoded) if tagged else decoded

            for capture in capture_boundaries.finish():
                yield (capture.modality, capture) if tagged else capture

            for stream in streams:
                modality = cast(Modality, stream.type)
                for frame in _decode_or_stop(stream.codec_context, None, stop_event):
                    decoded = DecodedFrame(frame)
                    yield (modality, decoded) if tagged else decoded
            sample_load(force=True)
            if is_rtsp_source(source) and not (stop_event is not None and stop_event.is_set()):
                raise LiveSourceInterruptedError("RTSP source ended unexpectedly")
    finally:
        stats = ring.stats
        telemetry.peak_buffer_bytes = max(
            telemetry.peak_buffer_bytes, stats.memory_bytes + stats.spill_bytes
        )
        telemetry.peak_memory_bytes = max(telemetry.peak_memory_bytes, stats.memory_bytes)
        telemetry.peak_spill_bytes = max(telemetry.peak_spill_bytes, stats.spill_bytes)
        ring.close()
