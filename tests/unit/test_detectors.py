from __future__ import annotations

import numpy as np
import pytest

from shsd.detectors import SignalObservation, analyze_audio, analyze_video_frames


def test_audio_silence_is_inactive_and_tone_has_rms_and_novelty() -> None:
    sample_rate = 16_000
    silence = np.zeros(sample_rate, dtype=np.float32)
    tone = np.concatenate(
        (
            silence[: sample_rate // 10],
            np.sin(
                2 * np.pi * 440 * np.arange(sample_rate - sample_rate // 10) / sample_rate
            ).astype(np.float32),
        )
    )

    silent_observations = analyze_audio(silence, sample_rate)
    tone_observations = analyze_audio(tone, sample_rate)

    assert silent_observations
    assert all(item.subtype != "onset" for item in silent_observations)
    assert all(
        item.value is False
        for item in silent_observations
        if item.subtype == "energy_vad"
    )
    assert any(item.subtype == "onset" for item in tone_observations)
    assert any(item.subtype == "rms" and item.value > 0.5 for item in tone_observations)
    assert all(item.method_version and 0 <= item.quality <= 1 for item in tone_observations)
    assert all(item.end_ms > item.start_ms for item in tone_observations)


def test_audio_rejects_invalid_sample_rate_and_accepts_multichannel() -> None:
    with pytest.raises(ValueError, match="sample_rate"):
        analyze_audio(np.zeros(100), 0)

    observations = analyze_audio(np.zeros((800, 2), dtype=np.int16), 16_000)
    assert observations
    assert {item.subtype for item in observations} >= {"rms", "energy_vad"}


def test_video_detects_scene_cut_but_not_a_static_frame() -> None:
    blue = np.zeros((180, 320, 3), dtype=np.uint8)
    green = np.zeros_like(blue)
    green[..., 1] = 255
    frames = [(0, blue), (1000, blue), (2000, green)]

    observations = analyze_video_frames(frames)

    differences = [item for item in observations if item.subtype == "frame_difference"]
    cuts = [item for item in observations if item.subtype == "scene_cut"]
    assert len(differences) == 2
    assert differences[0].value == 0
    assert differences[1].value > 0.25
    assert len(cuts) == 1
    assert (cuts[0].start_ms, cuts[0].end_ms) == (1000, 2000)


def test_video_scene_cut_uses_color_when_gray_luminance_is_similar() -> None:
    red = np.zeros((32, 32, 3), dtype=np.uint8)
    red[..., 0] = 255
    green = np.zeros_like(red)
    green[..., 1] = 255

    observations = analyze_video_frames([(0, red), (1000, green)])

    assert any(item.subtype == "scene_cut" and item.value is True for item in observations)
    difference = next(item for item in observations if item.subtype == "frame_difference")
    assert difference.unit == "mean_absolute_rgb_difference"


def test_video_detects_a_cut_that_changes_only_part_of_the_frame() -> None:
    before = np.zeros((100, 100, 3), dtype=np.uint8)
    after = before.copy()
    after[:, :30, 1] = 255

    observations = analyze_video_frames([(0, before), (1000, after)])

    difference = next(item for item in observations if item.subtype == "frame_difference")
    assert 0.08 <= difference.value < 0.25
    assert any(item.subtype == "scene_cut" and item.value is True for item in observations)


def test_observation_contract_is_json_compatible() -> None:
    observation = SignalObservation(0, 10, "rms", 1.0, "test-v1", 0.25, "full_scale")
    assert observation.to_dict() == {
        "start_ms": 0,
        "end_ms": 10,
        "subtype": "rms",
        "quality": 1.0,
        "method_version": "test-v1",
        "value": 0.25,
        "unit": "full_scale",
    }
