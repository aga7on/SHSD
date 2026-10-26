"""Fast and clock-paced replay with pause, resume, stop, and seek controls."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping
from threading import Condition, Event
from typing import Literal

from shsd.ingest.clock import MediaClock
from shsd.ingest.demux import DemuxPacket, iter_media_packets

ReplayMode = Literal["fast", "simulate_realtime"]


class ReplayController:
    """Replay a local file while keeping controls at packet boundaries.

    A seek discards any packet fetched from the old cursor, increments the
    clock epoch, and reopens the file at or before the requested source time.
    A paused packet stays pending until resume, so pause does not advance the
    visible cursor.
    """

    def __init__(
        self,
        source: str,
        clock: MediaClock,
        *,
        mode: ReplayMode = "fast",
        speed: float = 1.0,
        track_offsets_ms: Mapping[int, int] | None = None,
        on_epoch_started: Callable[[str, int], None] | None = None,
    ) -> None:
        if mode not in ("fast", "simulate_realtime"):
            raise ValueError(f"unsupported replay mode: {mode}")
        if speed <= 0:
            raise ValueError("speed must be positive")
        self.source = source
        self.clock = clock
        self.mode = mode
        self.speed = speed
        self.track_offsets_ms = dict(track_offsets_ms or {})
        self.on_epoch_started = on_epoch_started
        self._condition = Condition()
        self._stop_event = Event()
        self._paused = False
        self._stopped = False
        self._seek_target_ms: int | None = None
        self._started = False

    def pause(self) -> None:
        """Pause before the next packet is yielded."""
        with self._condition:
            self._paused = True
            self._condition.notify_all()

    def resume(self) -> None:
        """Resume at the pending packet or current source position."""
        with self._condition:
            self._paused = False
            self._condition.notify_all()

    def seek(self, target_ms: int) -> None:
        """Request a source-time seek; multiple pending requests coalesce."""
        if target_ms < 0:
            raise ValueError("seek target must be non-negative")
        with self._condition:
            if self._stopped:
                raise RuntimeError("cannot seek a stopped replay")
            self._seek_target_ms = target_ms
            self._condition.notify_all()

    def stop(self) -> None:
        """Stop replay and wake any paused or clock-paced iterator."""
        with self._condition:
            self._stopped = True
            self._stop_event.set()
            self._condition.notify_all()

    def packets(self) -> Iterator[DemuxPacket]:
        """Yield packets once, in demux order, applying requested controls."""
        with self._condition:
            if self._started:
                raise RuntimeError("ReplayController.packets() can be consumed only once")
            self._started = True

        notified_epoch: int | None = None

        def notify_epoch_started() -> None:
            nonlocal notified_epoch
            if notified_epoch == self.clock.epoch:
                return
            if self.on_epoch_started is not None:
                self.on_epoch_started(self.clock.stream_id, self.clock.epoch)
            notified_epoch = self.clock.epoch

        notify_epoch_started()
        seek_ms: int | None = None
        while True:
            with self._condition:
                if self._stopped:
                    return
                if self._seek_target_ms is not None:
                    seek_ms = self._seek_target_ms
                    self._seek_target_ms = None
                    self.clock.begin_epoch("seek")
                    notify_epoch_started()

            packet_iterator = iter_media_packets(
                self.source,
                self.clock,
                track_offsets_ms=self.track_offsets_ms,
                stop_event=self._stop_event,
                seek_ms=seek_ms,
            )
            media_anchor_ms: int | None = seek_ms
            wall_anchor: float | None = None
            seek_ms = None
            restart_at_ms: int | None = None
            try:
                for packet in packet_iterator:
                    notify_epoch_started()
                    while True:
                        with self._condition:
                            if self._stopped:
                                return
                            if self._seek_target_ms is not None:
                                restart_at_ms = self._seek_target_ms
                                self._seek_target_ms = None
                                self.clock.begin_epoch("seek")
                                notify_epoch_started()
                                break
                            if self._paused:
                                paused_at = time.monotonic()
                                while (
                                    self._paused
                                    and not self._stopped
                                    and self._seek_target_ms is None
                                ):
                                    self._condition.wait()
                                pause_duration = time.monotonic() - paused_at
                                if wall_anchor is not None:
                                    wall_anchor += pause_duration
                                continue
                            if self._stopped:
                                return

                            if self.mode == "simulate_realtime":
                                if media_anchor_ms is None:
                                    media_anchor_ms = packet.start_ms
                                    wall_anchor = time.monotonic()
                                assert wall_anchor is not None
                                media_elapsed_s = max(
                                    0, packet.start_ms - media_anchor_ms
                                ) / 1000 / self.speed
                                remaining_s = wall_anchor + media_elapsed_s - time.monotonic()
                                if remaining_s > 0:
                                    self._condition.wait(timeout=remaining_s)
                                    continue
                            break

                    if restart_at_ms is not None:
                        break
                    if self._stopped:
                        return
                    yield packet
            finally:
                packet_iterator.close()

            if restart_at_ms is None:
                return
            seek_ms = restart_at_ms
