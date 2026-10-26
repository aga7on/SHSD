from __future__ import annotations

import pytest
from scripts.probe_video_action_xclip import _scan_intervals


def test_scan_intervals_emits_ordered_windows_and_includes_end_boundary() -> None:
    intervals = _scan_intervals(0, 20_000, 8_000, 1_000)

    assert len(intervals) == 13
    assert intervals[0] == (0, 8_000)
    assert intervals[-1] == (12_000, 20_000)
    assert all(left[0] < right[0] for left, right in zip(intervals, intervals[1:], strict=False))
    assert all(left[1] >= right[0] for left, right in zip(intervals, intervals[1:], strict=False))


def test_scan_intervals_aligns_last_window_without_dropping_source_tail() -> None:
    intervals = _scan_intervals(1_000, 21_000, 8_000, 6_000)

    assert intervals == ((1_000, 9_000), (7_000, 15_000), (13_000, 21_000))


@pytest.mark.parametrize(
    ("start_ms", "end_ms", "window_ms", "stride_ms"),
    [
        (-1, 10_000, 8_000, 1_000),
        (0, 0, 8_000, 1_000),
        (0, 7_999, 8_000, 1_000),
        (0, 10_000, 0, 1_000),
        (0, 10_000, 8_000, 0),
        (0, 10_000, 8_000, 8_001),
    ],
)
def test_scan_intervals_rejects_invalid_ranges_or_stride(
    start_ms: int,
    end_ms: int,
    window_ms: int,
    stride_ms: int,
) -> None:
    with pytest.raises(ValueError):
        _scan_intervals(start_ms, end_ms, window_ms, stride_ms)
