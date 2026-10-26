from __future__ import annotations

from typing import cast

import numpy as np
import pytest

from shsd.detectors.types import SignalObservation
from shsd.sampling import AdaptiveSamplingController


def _sampling_counts(
    controller: AdaptiveSamplingController,
    modality: str,
) -> dict[str, int]:
    snapshot = controller.snapshot()
    modalities = cast(dict[str, dict[str, int]], snapshot["modalities"])
    return modalities[modality]


def _audio_changes(
    *,
    loudness_db: float = 0.0,
    activity_fraction: float = 0.0,
    centroid_hz: float = 0.0,
    onset_count: float = 0.0,
) -> list[SignalObservation]:
    return [
        SignalObservation(1_000, 2_000, subtype, 1.0, "test-v1", value, unit)
        for subtype, value, unit in (
            ("loudness_delta_db", loudness_db, "dB"),
            ("activity_fraction_delta", activity_fraction, "fraction"),
            ("spectral_centroid_delta_hz", centroid_hz, "Hz"),
            ("onset_count_delta", onset_count, "count"),
        )
    ]


def test_adaptive_audio_samples_on_window_changes_and_heartbeat() -> None:
    controller = AdaptiveSamplingController(
        profile="adaptive",
        window_ms=1_000,
        heartbeat_windows=3,
    )

    first = controller.select_audio(0, [], signal_changes=[])
    stable = controller.select_audio(1_000, [], signal_changes=_audio_changes())
    changed = controller.select_audio(
        2_000,
        [],
        signal_changes=_audio_changes(loudness_db=4.0),
    )
    heartbeat = controller.select_audio(5_000, [], signal_changes=_audio_changes())

    assert first.selected and first.reason == "uncomparable"
    assert not stable.selected and stable.reason == "stable_audio"
    assert changed.selected and changed.reason == "activity"
    assert heartbeat.selected and heartbeat.reason == "heartbeat"


def test_adaptive_audio_samples_when_window_comparison_is_unavailable() -> None:
    controller = AdaptiveSamplingController(profile="adaptive", window_ms=1_000)
    controller.select_audio(0, [], signal_changes=[])

    decision = controller.select_audio(1_000, [], signal_changes=None)

    assert decision.selected
    assert decision.reason == "uncomparable"
    assert _sampling_counts(controller, "audio")["uncomparable"] == 2


def test_adaptive_audio_change_waits_for_window_stride() -> None:
    controller = AdaptiveSamplingController(profile="adaptive", window_ms=2_000)
    controller.select_audio(0, [], signal_changes=[])

    decision = controller.select_audio(
        1_000,
        [],
        signal_changes=_audio_changes(loudness_db=10.0),
    )

    assert not decision.selected
    assert decision.reason == "stride_limited"
    assert _sampling_counts(controller, "audio")["stride_limited"] == 1


def test_standard_audio_profile_ignores_delta_and_keeps_every_window() -> None:
    controller = AdaptiveSamplingController(profile="standard", window_ms=1_000)

    first = controller.select_audio(0, [], signal_changes=[])
    second = controller.select_audio(1_000, [], signal_changes=_audio_changes())

    assert first.selected and first.reason == "standard"
    assert second.selected and second.reason == "standard"


def test_embedding_novelty_uses_last_accepted_compatible_vector() -> None:
    controller = AdaptiveSamplingController(profile="adaptive", window_ms=1_000)
    first_vector = np.zeros(768, dtype=np.float32)
    first_vector[0] = 1.0
    orthogonal_vector = np.zeros(768, dtype=np.float32)
    orthogonal_vector[1] = 1.0
    profile = {
        "model_revision": "embedding-v1",
        "preprocess_version": "preprocess-v1",
    }

    first = controller.compare_accepted_embedding(
        "audio",
        first_vector,
        **profile,
        window_id="window-0",
    )
    controller.accept_embedding(
        "audio",
        first_vector,
        **profile,
        window_id="window-0",
    )
    same = controller.compare_accepted_embedding(
        "audio",
        first_vector,
        **profile,
        window_id="window-1",
    )
    orthogonal = controller.compare_accepted_embedding(
        "audio",
        orthogonal_vector,
        **profile,
        window_id="window-2",
    )
    still_against_accepted = controller.compare_accepted_embedding(
        "audio",
        first_vector,
        **profile,
        window_id="window-3",
    )

    assert not first.comparable
    assert same.comparable and same.cosine_similarity == pytest.approx(1.0)
    assert same.novelty_score == pytest.approx(0.0)
    assert orthogonal.comparable and orthogonal.novelty_score == pytest.approx(1.0)
    assert still_against_accepted.reference_window_id == "window-0"


def test_embedding_novelty_resets_comparison_on_profile_change() -> None:
    controller = AdaptiveSamplingController(profile="adaptive", window_ms=1_000)
    vector = np.zeros(768, dtype=np.float32)
    vector[0] = 1.0
    controller.accept_embedding(
        "video",
        vector,
        model_revision="embedding-v1",
        preprocess_version="preprocess-v1",
        window_id="window-0",
    )

    result = controller.compare_accepted_embedding(
        "video",
        vector,
        model_revision="embedding-v2",
        preprocess_version="preprocess-v1",
        window_id="window-1",
    )

    assert not result.comparable
    assert result.cosine_similarity is None
    assert result.novelty_score is None
    assert result.reference_window_id == "window-0"


def test_adaptive_video_stride_under_runtime_pressure_is_bounded_and_visible() -> None:
    controller = AdaptiveSamplingController(
        profile="adaptive",
        window_ms=1_000,
        heartbeat_windows=3,
        video_difference_threshold=0.01,
    )
    dark = np.zeros((4, 4, 3), dtype=np.uint8)
    bright = np.full((4, 4, 3), 255, dtype=np.uint8)

    first = controller.select_video(0, dark, standard_due=False, minimum_stride_ms=2_000)
    throttled = controller.select_video(
        1_000,
        bright,
        standard_due=False,
        minimum_stride_ms=2_000,
    )
    after_stride = controller.select_video(
        2_000,
        dark,
        standard_due=False,
        minimum_stride_ms=2_000,
    )

    assert not first.selected
    assert first.reason == "runtime_backpressure"
    assert not throttled.selected
    assert throttled.reason == "runtime_backpressure"
    assert after_stride.selected
    assert _sampling_counts(controller, "video")["runtime_backpressure"] == 2


def test_video_pressure_stride_cannot_be_shorter_than_window() -> None:
    controller = AdaptiveSamplingController(profile="adaptive", window_ms=1_000)

    with pytest.raises(ValueError, match="cannot be shorter"):
        controller.select_video(
            0,
            np.zeros((4, 4, 3), dtype=np.uint8),
            standard_due=False,
            minimum_stride_ms=500,
        )


def test_rolled_back_video_sample_allows_retry_after_drop() -> None:
    controller = AdaptiveSamplingController(profile="adaptive", window_ms=1_000)
    frame = np.zeros((4, 4, 3), dtype=np.uint8)

    selected = controller.select_video(
        2_000,
        frame,
        standard_due=False,
        minimum_stride_ms=2_000,
    )
    controller.rollback_video_sample(2_000)
    retried = controller.select_video(
        2_100,
        frame,
        standard_due=False,
        minimum_stride_ms=2_000,
    )

    assert selected.selected
    assert retried.selected
