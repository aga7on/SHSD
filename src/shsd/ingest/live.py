"""Helpers for classifying transient live-source transport failures."""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn
from urllib.parse import urlsplit


class LiveSourceInterruptedError(RuntimeError):
    """An RTSP source could not be opened or ended while the job was active."""


def is_rtsp_source(source: str | Path) -> bool:
    """Return whether a source uses the RTSP transport supported by reconnects."""
    if not isinstance(source, str):
        return False
    return urlsplit(source).scheme.lower() in {"rtsp", "rtsps"}


def raise_live_source_error(source: str | Path, error: BaseException) -> NoReturn:
    """Wrap transport errors from RTSP while leaving other sources unchanged."""
    if is_rtsp_source(source):
        raise LiveSourceInterruptedError(f"RTSP source interrupted: {error}") from error
    raise error
