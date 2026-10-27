"""Lightweight, model-free signal measurements."""

from shsd.detectors.audio import analyze_audio
from shsd.detectors.novelty import compare_audio_windows
from shsd.detectors.types import SignalObservation
from shsd.detectors.video import analyze_video_frames, detect_motion_segments

__all__ = [
    "SignalObservation",
    "analyze_audio",
    "analyze_video_frames",
    "compare_audio_windows",
    "detect_motion_segments",
]
