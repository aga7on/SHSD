from __future__ import annotations

from fractions import Fraction

import pytest

from shsd.ingest.clock import EpochReason, MediaClock, pts_to_ms


def test_pts_conversion_uses_exact_rational_arithmetic() -> None:
    assert pts_to_ms(3, Fraction(1, 3)) == 1000
    assert pts_to_ms(1, (1, 2000)) == 1
    assert pts_to_ms(-1, (1, 2000)) == -1
    assert pts_to_ms(12, Fraction(1, 25), offset_ms=40) == 520


def test_variable_frame_times_and_track_offsets_share_source_epoch() -> None:
    clock = MediaClock("stream-a", max_forward_gap_ms=1000)

    first_video = clock.observe("video", 0, Fraction(1, 1000), duration_ms=40)
    audio = clock.observe("audio", 0, Fraction(1, 48_000), offset_ms=125, duration_ms=20)
    next_video = clock.observe("video", 67, Fraction(1, 1000), duration_ms=33)

    assert (first_video.timestamp_ms, audio.timestamp_ms, next_video.timestamp_ms) == (
        0,
        125,
        67,
    )
    assert first_video.epoch == audio.epoch == next_video.epoch == 0


def test_audio_and_video_offsets_align_within_one_frame() -> None:
    clock = MediaClock("stream-av")
    video = clock.observe("video", 3, Fraction(1, 10))
    audio = clock.observe("audio", 14_448, Fraction(1, 48_000))

    assert abs(video.timestamp_ms - audio.timestamp_ms) <= 40


def test_missing_pts_uses_flagged_same_track_fallback() -> None:
    clock = MediaClock("stream-a")
    first = clock.observe("video", 90, Fraction(1, 30), duration_ms=33)
    missing = clock.observe("video", None, None, duration_ms=33)

    assert first.timestamp_ms == 3000
    assert missing.timestamp_source == "fallback"
    assert missing.timestamp_ms == 3033
    assert missing.epoch == first.epoch


@pytest.mark.parametrize(
    ("pts", "duration_ms", "expected_reason"),
    [(900, 0, "backward_pts"), (5000, 40, "forward_gap")],
)
def test_discontinuity_starts_new_epoch(
    pts: int, duration_ms: int, expected_reason: str
) -> None:
    clock = MediaClock("stream-a", max_forward_gap_ms=1000)
    first = clock.observe("video", 1000, Fraction(1, 1000), duration_ms=40)
    next_point = clock.observe(
        "video", pts, Fraction(1, 1000), duration_ms=duration_ms
    )

    assert first.epoch == 0
    assert next_point.epoch == 1
    assert next_point.discontinuity == expected_reason
    assert clock.start_pts == pts


@pytest.mark.parametrize("reason", ["seek", "reconnect", "time_discontinuity"])
def test_explicit_epoch_reset(reason: EpochReason) -> None:
    clock = MediaClock("stream-a")
    clock.observe("video", 42, Fraction(1, 1000))

    assert clock.begin_epoch(reason) == 1
    point = clock.observe("video", 7, Fraction(1, 1000))

    assert point.epoch == 1
    assert point.timestamp_ms == 7
    assert point.discontinuity is None


def test_invalid_time_base_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive rational"):
        pts_to_ms(1, (1, 0))
