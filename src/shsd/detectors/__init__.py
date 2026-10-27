"""Lightweight, model-free signal measurements."""

from shsd.detectors.audio import analyze_audio
from shsd.detectors.novelty import compare_audio_windows, detect_audio_transitions
from shsd.detectors.types import SignalObservation
from shsd.detectors.video import analyze_video_frames, detect_motion_segments

__all__ = [
    "SignalObservation",
    "analyze_audio",
    "analyze_video_frames",
    "compare_audio_windows",
    "detect_audio_transitions",
    "detect_motion_segments",
]
