"""Bounded file-packet ingest with visible retention and host-pressure results."""

from __future__ import annotations

import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from shsd.ingest.clock import MediaClock
from shsd.ingest.demux import inspect_media
from shsd.ingest.replay import ReplayController, ReplayMode
from shsd.ingest.ring import (
    RING_MAX_CHUNKS,
    RING_MEMORY_BYTES,
    RING_SPILL_BYTES,
    RING_WINDOW_MS,
    DroppedChunk,
    MediaRing,
    default_spill_directory,
)
from shsd.memory.watermarks import WatermarkTracker
from shsd.workers.scheduler import LoadSample, RuntimeLoadController

DROP_SAMPLE_LIMIT = 100
HOST_SAMPLE_INTERVAL_S = 0.25


def _memory_limit_bytes() -> int:
    try:
        return max(0, int(os.environ.get("SHSD_MEMORY_LIMIT_BYTES", "0")))
    except ValueError:
        return 0


def replay_into_bounded_ring(
    source: str | Path,
    *,
    mode: ReplayMode,
    speed: float,
    stream_id: str,
) -> dict[str, Any]:
    """Demux a file into the rolling ring and report gaps and pressure.

    Packets that cannot fit in memory or bounded spill still advance C through
    an explicit dropped coverage span. Consumers may use the ring's leases to
    keep packets alive across the next stage. The analyzer uses the same ring
    limits and lease mechanism before PyAV decode, then schedules L2 events.
    """
    media = inspect_media(source)
    clock = MediaClock(stream_id)
    replay = ReplayController(str(source), clock, mode=mode, speed=speed)
    ring = MediaRing(
        window_ms=RING_WINDOW_MS,
        max_memory_bytes=RING_MEMORY_BYTES,
        max_chunks=RING_MAX_CHUNKS,
        spill_dir=default_spill_directory(),
        max_spill_bytes=RING_SPILL_BYTES,
    )
    tracker = (
        WatermarkTracker(
            stream_id,
            required_modalities=set(media.available_modalities),
        )
        if media.available_modalities
        else None
    )
    load_controller = RuntimeLoadController()
    counts = {"audio": 0, "video": 0}
    drop_counts = {"audio": 0, "video": 0}
    drop_samples: list[dict[str, object]] = []
    first_ms: int | None = None
    last_ms: int | None = None
    first_wall_time: float | None = None
    source_lag_ms = 0
    last_cpu_percent = 0.0
    current_rss_bytes = 0
    max_rss_bytes = 0
    host_sample_count = 0
    host_metrics_available = False
    psutil_module: Any = None
    process: Any = None
    last_host_sample = time.monotonic()

    try:
        import psutil

        psutil_module = psutil
        process = psutil_module.Process()
        psutil_module.cpu_percent(interval=None)  # prime the system CPU sample
        host_metrics_available = True
    except (ImportError, OSError):
        psutil_module = None
        process = None

    def sample_host(now: float, *, force: bool = False) -> None:
        nonlocal current_rss_bytes, host_metrics_available, host_sample_count
        nonlocal last_cpu_percent, last_host_sample, max_rss_bytes, process, psutil_module
        if process is None or psutil_module is None:
            return
        if not force and now - last_host_sample < HOST_SAMPLE_INTERVAL_S:
            return
        try:
            last_cpu_percent = min(
                100.0, max(0.0, float(psutil_module.cpu_percent(interval=None)))
            )
            current_rss_bytes = int(process.memory_info().rss)
            max_rss_bytes = max(max_rss_bytes, current_rss_bytes)
            host_sample_count += 1
            last_host_sample = now
        except Exception:
            # The optional host sensor must never stop packet capture.
            process = None
            psutil_module = None
            host_metrics_available = False

    def observe_pressure() -> None:
        stats = ring.stats
        buffered_bytes = stats.memory_bytes + stats.spill_bytes
        ring_capacity_bytes = RING_MEMORY_BYTES + RING_SPILL_BYTES
        load_controller.observe(
            LoadSample(
                queue_depth=buffered_bytes,
                queue_capacity=ring_capacity_bytes,
                source_lag_ms=source_lag_ms,
                cpu_percent=last_cpu_percent,
                rss_bytes=current_rss_bytes,
                memory_limit_bytes=_memory_limit_bytes(),
            )
        )

    try:
        for packet in replay.packets():
            now = time.monotonic()
            first_wall_time = now if first_wall_time is None else first_wall_time
            first_ms = packet.start_ms if first_ms is None else min(first_ms, packet.start_ms)
            packet_end_ms = max(packet.start_ms, packet.end_ms)
            last_ms = packet_end_ms if last_ms is None else max(last_ms, packet_end_ms)
            counts[packet.modality] += 1

            stored = ring.append(
                stream_id=packet.stream_id,
                epoch=packet.epoch,
                start_ms=packet.start_ms,
                end_ms=packet_end_ms,
                kind=packet.modality,
                data=packet.data,
                source_pts_range=packet.source_pts_range,
            )
            coverage_start = max(0, packet.start_ms)
            coverage_end = max(coverage_start + 1, packet.end_ms)
            if isinstance(stored, DroppedChunk):
                drop_counts[packet.modality] += 1
                if len(drop_samples) < DROP_SAMPLE_LIMIT:
                    drop_samples.append(
                        {
                            "packet_index": packet.packet_index,
                            "modality": packet.modality,
                            "start_ms": coverage_start,
                            "end_ms": coverage_end,
                            "reason": stored.reason,
                        }
                    )
                if tracker is not None:
                    tracker.mark(
                        "C",
                        coverage_start,
                        coverage_end,
                        "dropped",
                        modality=packet.modality,
                        reason=f"ring_{stored.reason}",
                    )
            elif tracker is not None:
                tracker.mark(
                    "C",
                    coverage_start,
                    coverage_end,
                    "done",
                    modality=packet.modality,
                )

            if mode == "simulate_realtime" and first_wall_time is not None:
                expected_elapsed_ms = round((now - first_wall_time) * 1000 * speed)
                actual_elapsed_ms = max(0, (last_ms or 0) - (first_ms or 0))
                source_lag_ms = max(0, expected_elapsed_ms - actual_elapsed_ms)
            sample_host(now)
            observe_pressure()

        sample_host(time.monotonic(), force=True)
        observe_pressure()
        stats = ring.stats
        final_snapshot = (
            tracker.snapshot(through_ms=max(0, last_ms or 0))
            if tracker is not None
            else None
        )
        capture_issues = (
            [
                asdict(issue)
                for issue in final_snapshot.issues
                if issue.stage == "C" and issue.status != "done"
            ]
            if final_snapshot is not None
            else []
        )
        buffer_bytes = stats.memory_bytes + stats.spill_bytes
        capacity_bytes = RING_MEMORY_BYTES + RING_SPILL_BYTES
        return {
            "schema_version": 1,
            "source": str(Path(source)),
            "stream_id": clock.stream_id,
            "epoch": clock.epoch,
            "mode": mode,
            "speed": speed,
            "packets": sum(counts.values()),
            "packets_by_modality": counts,
            "start_ms": first_ms,
            "end_ms": last_ms,
            "ring": {
                "window_ms": RING_WINDOW_MS,
                "chunk_count": stats.chunk_count,
                "max_chunks": RING_MAX_CHUNKS,
                "memory_bytes": stats.memory_bytes,
                "spill_bytes": stats.spill_bytes,
                "memory_capacity_bytes": RING_MEMORY_BYTES,
                "spill_capacity_bytes": RING_SPILL_BYTES,
                "occupancy_ratio": round(buffer_bytes / capacity_bytes, 6),
                "dropped_count": stats.dropped_count,
                "dropped_by_modality": drop_counts,
                "dropped_samples": drop_samples,
            },
            "capture": {
                "C_ms": final_snapshot.C_ms if final_snapshot is not None else 0,
                "modality_cursors": {
                    modality: cursors["C"]
                    for modality, cursors in (
                        final_snapshot.modality_cursors.items()
                        if final_snapshot is not None
                        else ()
                    )
                },
                "issues": capture_issues[:DROP_SAMPLE_LIMIT],
                "issue_sample_limit": DROP_SAMPLE_LIMIT,
            },
            "host": {
                "metrics_available": host_metrics_available,
                "sample_count": host_sample_count,
                "cpu_percent": round(last_cpu_percent, 2),
                "rss_bytes": current_rss_bytes,
                "max_rss_bytes": max_rss_bytes,
                "memory_limit_bytes": _memory_limit_bytes(),
                "load": load_controller.status.to_dict(),
            },
        }
    finally:
        replay.stop()
        ring.close()
