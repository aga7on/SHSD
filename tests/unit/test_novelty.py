from __future__ import annotations

import numpy as np
import pytest

from shsd.detectors import analyze_audio, compare_audio_windows
from shsd.detectors.types import SignalObservation


def _tone(amplitude: float, frequency_hz: float = 440.0) -> np.ndarray:
    time = np.arange(16_000, dtype=np.float32) / 16_000
    return (amplitude * np.sin(2 * np.pi * frequency_hz * time)).astype(np.float32)


def _compare(
    previous: np.ndarray,
    current: np.ndarray,
    *,
    current_start_ms: int = 1000,
) -> tuple[list[SignalObservation], list[SignalObservation], list[SignalObservation]]:
    before = analyze_audio(previous, 16_000, start_ms=0)
    after = analyze_audio(current, 16_000, start_ms=current_start_ms)
    return before, after, compare_audio_windows(before, after)


def test_audio_window_delta_reports_no_change_for_silence() -> None:
    silence = np.zeros(16_000, dtype=np.float32)

    _, _, deltas = _compare(silence, silence)

    assert {item.subtype for item in deltas} == {
        "rms_delta",
        "loudness_delta_db",
        "onset_count_delta",
        "activity_fraction_delta",
        "spectral_centroid_delta_hz",
    }
    assert all(item.value == 0 for item in deltas)
    assert all("instrument" not in item.subtype for item in deltas)


def test_audio_window_delta_detects_new_audio_and_level_increase() -> None:
    silence = np.zeros(16_000, dtype=np.float32)

    _, _, started = _compare(silence, _tone(0.1))
    started_by_name = {item.subtype: item for item in started}
    assert started_by_name["rms_delta"].value > 0
    assert started_by_name["spectral_centroid_delta_hz"].value > 400

    _, _, louder = _compare(_tone(0.1), _tone(0.5))
    louder_by_name = {item.subtype: item for item in louder}
    assert louder_by_name["loudness_delta_db"].value == pytest.approx(14.0, abs=0.2)
    assert louder_by_name["rms_delta"].value > 0


def test_audio_window_delta_detects_spectral_change_without_level_change() -> None:
    _, _, deltas = _compare(
        _tone(0.2, 220.0),
        _tone(0.2, 880.0),
    )
    values = {item.subtype: item for item in deltas}

    assert abs(values["rms_delta"].value) < 0.001
    assert values["spectral_centroid_delta_hz"].value > 500


def test_audio_window_delta_ignores_overlapping_intervals() -> None:
    tone = _tone(0.2)
    before = analyze_audio(tone, 16_000, start_ms=0)
    overlapping = analyze_audio(tone, 16_000, start_ms=500)

    assert compare_audio_windows(before, overlapping) == []
