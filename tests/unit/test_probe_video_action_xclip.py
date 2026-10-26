from __future__ import annotations

import numpy as np
import pytest
from scripts.probe_video_action_xclip import _pixel_change_summary, _scan_intervals


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


def test_pixel_change_summary_reports_full_and_center_crop_difference() -> None:
    left = np.zeros((8, 8, 3), dtype=np.uint8)
    right = left.copy()
    right[[0, 1, 6, 7], :, :] = 255
    right[:, [0, 1, 6, 7], :] = 255

    result = _pixel_change_summary(left, right)

    assert result["full_frame_mean_abs_rgb_delta"] == pytest.approx(191.25)
    assert result["center_crop_mean_abs_rgb_delta"] == 0


def test_pixel_change_summary_rejects_mismatched_or_non_rgb_frames() -> None:
    with pytest.raises(ValueError, match="matching"):
        _pixel_change_summary(np.zeros((8, 8, 3)), np.zeros((7, 8, 3)))
    with pytest.raises(ValueError, match="matching"):
        _pixel_change_summary(np.zeros((8, 8)), np.zeros((8, 8)))


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
