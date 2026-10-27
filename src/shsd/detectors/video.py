"""Downscaled frame-difference and scene-cut measurements."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from numpy.typing import ArrayLike

from shsd.detectors.types import SignalObservation

VIDEO_METHOD_VERSION = "video-frame-diff-v3"


def _downscaled_color(frame: ArrayLike, width: int, height: int) -> np.ndarray:
    image = np.asarray(frame)
    if np.issubdtype(image.dtype, np.integer):
        scale = float(np.iinfo(image.dtype).max)
        image = image.astype(np.float32) / scale
    else:
        image = image.astype(np.float32, copy=False)
    if image.ndim == 2:
        color = np.repeat(image[..., None], 3, axis=2)
    elif image.ndim == 3 and image.shape[2] in (3, 4):
        color = image[..., :3]
    else:
        raise ValueError("video frames must be grayscale or RGB/RGBA arrays")
    if color.shape[0] < 1 or color.shape[1] < 1:
        raise ValueError("video frames must have non-zero width and height")

    normalized = color.astype(np.float32, copy=False)
    if not np.issubdtype(np.asarray(frame).dtype, np.integer):
        peak = float(np.nanmax(normalized)) if normalized.size else 0.0
        if peak > 1.0:
            normalized = normalized / 255.0
    normalized = np.nan_to_num(normalized, copy=False, nan=0.0, posinf=1.0, neginf=0.0)
    y = np.rint(
        np.linspace(0, normalized.shape[0] - 1, min(height, normalized.shape[0]))
    ).astype(int)
    x = np.rint(
        np.linspace(0, normalized.shape[1] - 1, min(width, normalized.shape[1]))
    ).astype(int)
    return np.clip(normalized[y[:, None], x[None, :], :], 0.0, 1.0)


def analyze_video_frames(
    frames: Iterable[tuple[int, ArrayLike]],
    *,
    width: int = 160,
    height: int = 90,
    scene_cut_threshold: float = 0.08,
) -> list[SignalObservation]:
    """Compare consecutive color frames after nearest-neighbor downscaling.

    Each frame is `(source_timestamp_ms, image_array)`. A scene cut is a large
    pixel change; it does not imply a semantic scene description.
    """
    if width <= 0 or height <= 0:
        raise ValueError("downscaled frame dimensions must be positive")
    if not 0.0 <= scene_cut_threshold <= 1.0:
        raise ValueError("scene_cut_threshold must be between 0 and 1")

    observations: list[SignalObservation] = []
    previous_ms: int | None = None
    previous_color: np.ndarray | None = None
    for timestamp_ms, frame in frames:
        if timestamp_ms < 0:
            raise ValueError("frame timestamp must be non-negative")
        color = _downscaled_color(frame, width, height)
        if previous_color is not None and previous_ms is not None:
            if timestamp_ms <= previous_ms:
                raise ValueError("frame timestamps must be strictly increasing")
            score = float(np.abs(color - previous_color).mean())
            start_ms = previous_ms
            end_ms = timestamp_ms
            observations.append(
                SignalObservation(
                    start_ms,
                    end_ms,
                    "frame_difference",
                    1.0,
                    VIDEO_METHOD_VERSION,
                    score,
                    "mean_absolute_rgb_difference",
                )
            )
            if score >= scene_cut_threshold:
                observations.append(
                    SignalObservation(
                        start_ms,
                        end_ms,
                        "scene_cut",
                        min(1.0, score / max(scene_cut_threshold, 1e-12)),
                        VIDEO_METHOD_VERSION,
                        True,
                        "boolean",
                    )
                )
        previous_ms = timestamp_ms
        previous_color = color
    return observations


def detect_motion_segments(
    frames: Iterable[tuple[int, ArrayLike]],
    *,
    width: int = 160,
    height: int = 90,
    motion_threshold: float = 0.02,
    min_duration_ms: int = 500,
) -> list[tuple[int, int, float, int]]:
    """Group consecutive frame pairs with sustained pixel change into motion intervals.

    Returns (start_ms, end_ms, mean_diff, frame_count) for each segment. This is
    a motion boundary signal, not a semantic action label; callers must not
    treat it as an entity/action fact without independent verification.
    """
    if width <= 0 or height <= 0:
        raise ValueError("downscaled frame dimensions must be positive")
    if motion_threshold < 0:
        raise ValueError("motion_threshold must be non-negative")
    if min_duration_ms < 0:
        raise ValueError("min_duration_ms must be non-negative")

    samples: list[tuple[int, int, float]] = []
    previous_ms: int | None = None
    previous_color: np.ndarray | None = None
    for timestamp_ms, frame in frames:
        if timestamp_ms < 0:
            raise ValueError("frame timestamp must be non-negative")
        color = _downscaled_color(frame, width, height)
        if previous_color is not None and previous_ms is not None:
            if timestamp_ms <= previous_ms:
                raise ValueError("frame timestamps must be strictly increasing")
            score = float(np.abs(color - previous_color).mean())
            samples.append((previous_ms, timestamp_ms, score))
        previous_ms = timestamp_ms
        previous_color = color

    segments: list[tuple[int, int, float, int]] = []
    current: list[tuple[int, int, float]] = []
    for start_ms, end_ms, score in samples:
        if score >= motion_threshold:
            current.append((start_ms, end_ms, score))
        else:
            if current:
                span_ms = current[-1][1] - current[0][0]
                if span_ms >= min_duration_ms:
                    mean_diff = float(np.mean([item[2] for item in current]))
                    segments.append(
                        (current[0][0], current[-1][1], mean_diff, len(current))
                    )
                current = []
    if current:
        span_ms = current[-1][1] - current[0][0]
        if span_ms >= min_duration_ms:
            mean_diff = float(np.mean([item[2] for item in current]))
            segments.append((current[0][0], current[-1][1], mean_diff, len(current)))
    return segments
