"""Cheap RMS, loudness, energy VAD, and spectral novelty measurements."""

from __future__ import annotations

import math
from typing import cast

import numpy as np
from numpy.typing import ArrayLike

from shsd.detectors.types import SignalObservation

AUDIO_METHOD_VERSION = "audio-signal-v2"


def _mono_float32(samples: ArrayLike) -> np.ndarray:
    audio = np.asarray(samples)
    if np.issubdtype(audio.dtype, np.integer):
        scale = float(max(abs(np.iinfo(audio.dtype).min), np.iinfo(audio.dtype).max))
        audio = audio.astype(np.float32) / scale
    else:
        audio = audio.astype(np.float32, copy=False)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    elif audio.ndim != 1:
        raise ValueError("audio samples must be a mono vector or (samples, channels) matrix")
    if audio.size == 0:
        raise ValueError("audio samples must not be empty")
    return cast(
        np.ndarray,
        np.nan_to_num(audio, copy=False, nan=0.0, posinf=0.0, neginf=0.0),
    )


def analyze_audio(
    samples: ArrayLike,
    sample_rate: int,
    *,
    start_ms: int = 0,
    frame_ms: int = 25,
    hop_ms: int = 10,
    vad_threshold_dbfs: float = -42.0,
    onset_threshold: float = 0.18,
) -> list[SignalObservation]:
    """Measure audio without naming its source or semantic content.

    `energy_vad` is a thresholded activity estimate, not speech recognition.
    `spectral_novelty` and `onset` describe changes in the short-time spectrum.
    All intervals use source milliseconds and are half-open.
    """
    if sample_rate <= 0 or start_ms < 0:
        raise ValueError("sample_rate must be positive and start_ms must be non-negative")
    if frame_ms <= 0 or hop_ms <= 0 or hop_ms > frame_ms:
        raise ValueError("frame_ms and hop_ms must be positive, with hop_ms <= frame_ms")
    if not math.isfinite(vad_threshold_dbfs) or not math.isfinite(onset_threshold):
        raise ValueError("detector thresholds must be finite")
    if onset_threshold < 0:
        raise ValueError("onset_threshold must be non-negative")

    audio = _mono_float32(samples)
    frame_len = max(1, round(sample_rate * frame_ms / 1000))
    hop_len = max(1, round(sample_rate * hop_ms / 1000))
    fft_len = 1 << (frame_len - 1).bit_length()
    window = np.hanning(frame_len).astype(np.float32)
    previous_spectrum: np.ndarray | None = None
    observations: list[SignalObservation] = []

    for offset in range(0, audio.size, hop_len):
        valid_end = min(offset + frame_len, audio.size)
        frame = np.zeros(frame_len, dtype=np.float32)
        valid = audio[offset:valid_end]
        frame[: valid.size] = valid
        start = start_ms + round(offset * 1000 / sample_rate)
        end = start_ms + round(valid_end * 1000 / sample_rate)
        if end <= start:
            end = start + 1

        rms = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))
        dbfs = 20.0 * math.log10(max(rms, 1e-8))
        margin = abs(dbfs - vad_threshold_dbfs)
        vad_quality = min(1.0, margin / 12.0)
        valid_quality = valid.size / frame_len
        observations.extend(
            (
                SignalObservation(
                    start,
                    end,
                    "rms",
                    valid_quality,
                    AUDIO_METHOD_VERSION,
                    rms,
                    "full_scale",
                ),
                SignalObservation(
                    start,
                    end,
                    "loudness_dbfs",
                    valid_quality,
                    AUDIO_METHOD_VERSION,
                    dbfs,
                    "dBFS",
                ),
                SignalObservation(
                    start,
                    end,
                    "energy_vad",
                    vad_quality,
                    AUDIO_METHOD_VERSION,
                    dbfs >= vad_threshold_dbfs,
                    "boolean",
                ),
            )
        )

        spectrum = np.abs(np.fft.rfft(frame * window, n=fft_len)).astype(np.float32)
        frequency_bins = np.fft.rfftfreq(fft_len, d=1.0 / sample_rate)
        spectral_mass = float(spectrum.sum())
        centroid_hz = (
            float(np.dot(frequency_bins, spectrum) / spectral_mass)
            if spectral_mass > 1e-12
            else 0.0
        )
        observations.append(
            SignalObservation(
                start,
                end,
                "spectral_centroid",
                valid_quality,
                AUDIO_METHOD_VERSION,
                centroid_hz,
                "Hz",
            )
        )
        normalized = spectrum / max(float(spectrum.sum()), 1e-12)
        novelty = (
            0.0
            if previous_spectrum is None
            else float(np.maximum(normalized - previous_spectrum, 0.0).sum())
        )
        novelty_quality = min(1.0, novelty / max(onset_threshold, 1e-12))
        observations.append(
            SignalObservation(
                start,
                end,
                "spectral_novelty",
                novelty_quality,
                AUDIO_METHOD_VERSION,
                novelty,
                "normalized_flux",
            )
        )
        if previous_spectrum is not None and novelty >= onset_threshold:
            observations.append(
                SignalObservation(
                    start,
                    end,
                    "onset",
                    novelty_quality,
                    AUDIO_METHOD_VERSION,
                    novelty,
                    "normalized_flux",
                )
            )
        previous_spectrum = normalized

    return observations
