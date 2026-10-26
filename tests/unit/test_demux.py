from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from threading import Event

import pytest

from shsd.ingest.clock import MediaClock
from shsd.ingest.decoder import _decode_or_stop, _iter_source_packets
from shsd.ingest.demux import inspect_media, iter_media_packets
from shsd.ingest.live import LiveSourceInterruptedError

MEDIA = Path(__file__).parents[1] / "fixtures" / "media"


@pytest.mark.parametrize(
    ("filename", "expected_modalities"),
    [
        ("av_sync_20s.mp4", {"audio", "video"}),
        ("av_sync_20s.mkv", {"audio", "video"}),
        ("audio_music_10s.wav", {"audio"}),
        ("audio_speech_ru.wav", {"audio"}),
        ("audio_silence_5s.wav", {"audio"}),
        ("audio_sine_5s.wav", {"audio"}),
        ("video_motion_8s.mp4", {"video"}),
        ("video_scene_cuts_8s.mp4", {"video"}),
        ("video_static_3s.mp4", {"video"}),
    ],
)
def test_demux_streams_fixtures_and_marks_missing_modalities(
    filename: str, expected_modalities: set[str]
) -> None:
    source = MEDIA / filename
    clock = MediaClock(f"fixture-{source.stem}", max_forward_gap_ms=None)
    info = inspect_media(source)
    packets = iter_media_packets(source, clock)
    counts: dict[str, int] = defaultdict(int)
    last_packet_index: dict[int, int] = {}
    saw_pts = False

    for packet in packets:
        counts[packet.modality] += 1
        saw_pts |= packet.pts is not None
        assert packet.data
        assert packet.end_ms >= packet.start_ms
        assert packet.stream_id == clock.stream_id
        assert packet.epoch == clock.epoch
        assert packet.time_base > 0
        assert packet.packet_index == last_packet_index.get(packet.stream_index, -1) + 1
        last_packet_index[packet.stream_index] = packet.packet_index

    assert set(info.available_modalities) == expected_modalities
    assert set(info.unavailable_modalities) == {"audio", "video"} - expected_modalities
    assert set(counts) == expected_modalities
    assert sum(counts.values()) > 0
    assert saw_pts


def test_demux_preserves_source_pts_time_base_and_track_offset() -> None:
    source = MEDIA / "av_sync_20s.mp4"
    info = inspect_media(source)
    video_track = next(track for track in info.tracks if track.modality == "video")
    clock = MediaClock("fixture-av", max_forward_gap_ms=None)
    first_video = next(
        packet
        for packet in iter_media_packets(
            source, clock, track_offsets_ms={video_track.stream_index: 125}
        )
        if packet.modality == "video"
    )

    assert first_video.pts == 0
    assert first_video.time_base == video_track.time_base
    assert first_video.offset_ms == 125
    assert first_video.start_ms == 125
    assert first_video.source_pts_range == (0, 9000)
    assert first_video.duration_ms == 100


def test_demux_stops_cleanly_when_requested() -> None:
    stop_event = Event()
    stop_event.set()
    packets = iter_media_packets(
        MEDIA / "av_sync_20s.mp4", MediaClock("stopped"), stop_event=stop_event
    )

    assert list(packets) == []


def test_rtsp_open_io_error_is_classified_for_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_to_open(*_args: object, **_kwargs: object) -> object:
        raise OSError("publisher is offline")

    monkeypatch.setattr("shsd.ingest.demux.av.open", fail_to_open)

    with pytest.raises(LiveSourceInterruptedError, match="RTSP source interrupted"):
        inspect_media("rtsp://127.0.0.1:8554/offline")


def test_rtsp_read_error_during_stop_is_treated_as_graceful_eof() -> None:
    class StalledContainer:
        def demux(self, *_streams: object) -> object:
            raise OSError("read interrupted by stop")

    stop_event = Event()
    stop_event.set()

    assert list(
        _iter_source_packets(
            StalledContainer(), [], "rtsp://127.0.0.1:8554/live", stop_event=stop_event
        )
    ) == []


def test_rtsp_read_error_without_stop_remains_retryable() -> None:
    class StalledContainer:
        def demux(self, *_streams: object) -> object:
            raise OSError("publisher disconnected")

    with pytest.raises(LiveSourceInterruptedError, match="RTSP source interrupted"):
        list(_iter_source_packets(StalledContainer(), [], "rtsp://127.0.0.1:8554/live"))


def test_decoder_shutdown_error_is_ignored_only_after_explicit_stop() -> None:
    class BrokenDecoder:
        def decode(self, _packet: object) -> list[object]:
            raise RuntimeError("decoder flush interrupted")

    stop_event = Event()
    stop_event.set()
    assert _decode_or_stop(BrokenDecoder(), None, stop_event) == []

    stop_event.clear()
    with pytest.raises(RuntimeError, match="decoder flush interrupted"):
        _decode_or_stop(BrokenDecoder(), None, stop_event)
