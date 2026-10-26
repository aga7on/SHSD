"""Compare measured audio features across non-overlapping source windows."""

from __future__ import annotations

from shsd.detectors.types import SignalObservation

AUDIO_DELTA_METHOD_VERSION = "audio-window-delta-v1"


def _values(observations: list[SignalObservation], subtype: str) -> list[float]:
    return [
        float(item.value)
        for item in observations
        if item.subtype == subtype and isinstance(item.value, (int, float))
    ]


def compare_audio_windows(
    previous: list[SignalObservation], current: list[SignalObservation]
) -> list[SignalObservation]:
    """Return measured RMS, loudness, onset, activity, and centroid deltas.

    Overlapping or out-of-order intervals are not comparable and return no
    measurements. The deltas describe signal changes; they do not name a source
    or instrument.
    """
    if not previous or not current:
        raise ValueError("both audio windows must contain signal observations")
    previous_end = max(item.end_ms for item in previous)
    current_start = min(item.start_ms for item in current)
    current_end = max(item.end_ms for item in current)
    if current_start < previous_end or current_end <= current_start:
        return []

    def mean(items: list[SignalObservation], subtype: str) -> float:
        values = _values(items, subtype)
        if not values:
            raise ValueError(f"audio window is missing {subtype} observations")
        return sum(values) / len(values)

    previous_activity = mean(previous, "energy_vad")
    current_activity = mean(current, "energy_vad")
    previous_onsets = len(_values(previous, "onset"))
    current_onsets = len(_values(current, "onset"))
    quality = min(
        min(item.quality for item in previous if item.subtype == "rms"),
        min(item.quality for item in current if item.subtype == "rms"),
    )
    measurements = (
        (
            "rms_delta",
            mean(current, "rms") - mean(previous, "rms"),
            "full_scale",
        ),
        (
            "loudness_delta_db",
            mean(current, "loudness_dbfs") - mean(previous, "loudness_dbfs"),
            "dB",
        ),
        ("onset_count_delta", float(current_onsets - previous_onsets), "count"),
        ("activity_fraction_delta", current_activity - previous_activity, "fraction"),
        (
            "spectral_centroid_delta_hz",
            mean(current, "spectral_centroid") - mean(previous, "spectral_centroid"),
            "Hz",
        ),
    )
    return [
        SignalObservation(
            current_start,
            current_end,
            subtype,
            quality,
            AUDIO_DELTA_METHOD_VERSION,
            value,
            unit,
        )
        for subtype, value, unit in measurements
    ]
