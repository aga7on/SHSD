"""Streaming demux of audio/video packets with source timing metadata."""

from __future__ import annotations

from collections.abc import Generator, Mapping
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from threading import Event
from typing import Literal, cast
from urllib.parse import urlsplit

import av

from shsd.ingest.clock import MediaClock, pts_to_ms
from shsd.ingest.live import raise_live_source_error

Modality = Literal["audio", "video"]
TimestampSource = Literal["pts", "dts_fallback", "sequence_fallback"]


@dataclass(frozen=True, slots=True)
class MediaTrackInfo:
    """Codec and stream timing information read from a media container."""

    stream_index: int
    modality: Modality
    codec_name: str | None
    time_base: Fraction | None
    start_pts: int | None
    duration_pts: int | None
    width: int | None = None
    height: int | None = None
    sample_rate: int | None = None
    channels: int | None = None


@dataclass(frozen=True, slots=True)
class MediaSourceInfo:
    """Tracks present in a source and modalities explicitly unavailable."""

    source: str | Path
    tracks: tuple[MediaTrackInfo, ...]
    available_modalities: tuple[Modality, ...]
    unavailable_modalities: tuple[Modality, ...]


@dataclass(frozen=True, slots=True)
class DemuxPacket:
    """One compressed media packet; ``data`` is bounded to this packet."""

    stream_id: str
    epoch: int
    stream_index: int
    packet_index: int
    modality: Modality
    codec_name: str | None
    pts: int | None
    dts: int | None
    duration_pts: int | None
    time_base: Fraction
    offset_ms: int
    start_ms: int
    duration_ms: int | None
    timestamp_source: TimestampSource
    is_keyframe: bool
    data: bytes

    @property
    def end_ms(self) -> int:
        """Return the half-open source interval end when packet duration is known."""
        timestamp_pts = self.pts if self.pts is not None else self.dts
        if timestamp_pts is not None and self.duration_pts is not None:
            return pts_to_ms(
                timestamp_pts + self.duration_pts,
                self.time_base,
                offset_ms=self.offset_ms,
            )
        return self.start_ms + (self.duration_ms or 0)

    @property
    def source_pts_range(self) -> tuple[int, int] | None:
        """Return the source-clock PTS range without rounding it to milliseconds."""
        if self.pts is None:
            return None
        return self.pts, self.pts + (self.duration_pts or 0)


def open_media_container(source: str | Path) -> av.container.InputContainer:
    """Open local or network media and classify RTSP transport failures."""
    source_path = source if isinstance(source, Path) else str(source)
    timeout = (
        (15.0, 3.0)
        if isinstance(source_path, str)
        and urlsplit(source_path).scheme.lower() in {"http", "https", "rtsp", "rtsps"}
        else None
    )
    try:
        if timeout is None:
            return av.open(str(source_path), mode="r")
        return av.open(str(source_path), mode="r", timeout=timeout)
    except (av.error.FFmpegError, OSError) as error:
        raise_live_source_error(source, error)


def inspect_media(source: str | Path) -> MediaSourceInfo:
    """Read stream metadata without decoding or buffering media packets."""
    source_path = source if isinstance(source, Path) else str(source)
    tracks: list[MediaTrackInfo] = []
    with open_media_container(source) as container:
        for stream in container.streams:
            if stream.type not in ("audio", "video"):
                continue
            context = stream.codec_context
            raw_time_base = stream.time_base
            time_base = (
                Fraction(int(raw_time_base.numerator), int(raw_time_base.denominator))
                if raw_time_base is not None
                else None
            )
            modality: Modality = stream.type
            tracks.append(
                MediaTrackInfo(
                    stream_index=stream.index,
                    modality=modality,
                    codec_name=context.name,
                    time_base=time_base,
                    start_pts=stream.start_time,
                    duration_pts=stream.duration,
                    width=getattr(context, "width", None) if modality == "video" else None,
                    height=getattr(context, "height", None) if modality == "video" else None,
                    sample_rate=(
                        getattr(context, "sample_rate", None) if modality == "audio" else None
                    ),
                    channels=getattr(context, "channels", None) if modality == "audio" else None,
                )
            )

    present = {track.modality for track in tracks}
    modality_order: tuple[Modality, ...] = ("audio", "video")
    return MediaSourceInfo(
        source=source_path,
        tracks=tuple(tracks),
        available_modalities=tuple(kind for kind in modality_order if kind in present),
        unavailable_modalities=tuple(kind for kind in modality_order if kind not in present),
    )


def iter_media_packets(
    source: str | Path,
    clock: MediaClock,
    *,
    track_offsets_ms: Mapping[int, int] | None = None,
    stop_event: Event | None = None,
    seek_ms: int | None = None,
) -> Generator[DemuxPacket, None, None]:
    """Yield compressed audio/video packets in container demux order.

    Only one PyAV packet is converted to bytes at a time. PTS and DTS remain
    available in their original time base. A missing PTS uses DTS when present,
    otherwise a clearly marked same-track sequence fallback. Seeking or
    reconnecting is controlled by the caller through ``clock.begin_epoch``.
    """
    if stop_event is not None and stop_event.is_set():
        return
    source_path = source if isinstance(source, Path) else str(source)
    offsets = track_offsets_ms or {}
    packet_indices: dict[int, int] = {}
    fallback_ends_ms: dict[int, int] = {}
    if seek_ms is not None and seek_ms < 0:
        raise ValueError("seek_ms must be non-negative")
    with av.open(str(source_path), mode="r") as container:
        streams = [stream for stream in container.streams if stream.type in ("audio", "video")]
        if not streams:
            return
        if seek_ms is not None:
            seek_stream = next((stream for stream in streams if stream.type == "video"), streams[0])
            seek_time_base = seek_stream.time_base
            if seek_time_base is None:
                raise ValueError(f"stream {seek_stream.index} has no usable time_base")
            offset_ms = offsets.get(seek_stream.index, 0)
            ticks = Fraction(seek_ms - offset_ms, 1000) / Fraction(
                int(seek_time_base.numerator), int(seek_time_base.denominator)
            )
            seek_pts = ticks.numerator // ticks.denominator
            container.seek(seek_pts, stream=seek_stream, backward=True, any_frame=False)
        for packet in container.demux(*streams):
            if stop_event is not None and stop_event.is_set():
                return
            if packet.size <= 0:
                continue

            stream = packet.stream
            modality = cast(Modality, stream.type)
            raw_time_base = packet.time_base or stream.time_base
            if raw_time_base is None:
                raise ValueError(f"stream {stream.index} has no usable time_base")
            time_base = Fraction(int(raw_time_base.numerator), int(raw_time_base.denominator))
            offset_ms = offsets.get(stream.index, 0)
            pts = packet.pts
            dts = packet.dts
            clock.record_epoch_start_pts(pts)
            raw_duration = packet.duration
            duration_pts = raw_duration if raw_duration is not None and raw_duration > 0 else None
            duration_ms = pts_to_ms(duration_pts, time_base) if duration_pts is not None else None

            if pts is not None:
                start_ms = pts_to_ms(pts, time_base, offset_ms=offset_ms)
                timestamp_source: TimestampSource = "pts"
            elif dts is not None:
                start_ms = pts_to_ms(dts, time_base, offset_ms=offset_ms)
                timestamp_source = "dts_fallback"
            else:
                start_ms = fallback_ends_ms.get(stream.index, offset_ms)
                timestamp_source = "sequence_fallback"

            packet_index = packet_indices.get(stream.index, 0)
            packet_indices[stream.index] = packet_index + 1
            packet_end_ms = start_ms + (duration_ms or 0)
            fallback_ends_ms[stream.index] = packet_end_ms
            yield DemuxPacket(
                stream_id=clock.stream_id,
                epoch=clock.epoch,
                stream_index=stream.index,
                packet_index=packet_index,
                modality=modality,
                codec_name=stream.codec_context.name,
                pts=pts,
                dts=dts,
                duration_pts=duration_pts,
                time_base=time_base,
                offset_ms=offset_ms,
                start_ms=start_ms,
                duration_ms=duration_ms,
                timestamp_source=timestamp_source,
                is_keyframe=packet.is_keyframe,
                data=bytes(packet),
            )
