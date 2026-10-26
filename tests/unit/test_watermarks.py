from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from shsd.memory import StaleCoverageRevisionError, WatermarkTracker


def test_watermarks_wait_for_each_required_modality_and_keep_lag_per_level() -> None:
    tracker = WatermarkTracker("stream-1", required_modalities={"audio", "video"})
    tracker.mark("C", 0, 1000, "done", modality="audio")
    tracker.mark("C", 0, 500, "done", modality="video")
    tracker.mark("C", 500, 1000, "pending", modality="video")
    tracker.mark("E", 0, 1000, "done", modality="audio")
    tracker.mark("E", 0, 500, "done", modality="video")
    tracker.mark("E", 500, 1000, "unavailable", modality="video", reason="no frames")
    tracker.mark("D", 0, 400, "done", level="L1")
    tracker.mark("D", 400, 1000, "gap", level="L1", reason="analysis gap")
    tracker.mark("R", 0, 500, "done", level="L1")
    tracker.mark("R", 500, 1000, "pending", level="L1")

    snapshot = tracker.snapshot(through_ms=1000)
    assert snapshot.C_ms == 500
    assert snapshot.E_ms == 1000
    assert snapshot.D_ms["L1"] == 1000
    assert snapshot.R_ms["L1"] == 500
    assert snapshot.lag_ms["L1"] == 0  # C is still held at 500 by video.
    assert snapshot.modality_cursors["audio"]["C"] == 1000
    assert snapshot.modality_cursors["video"]["E"] == 1000
    assert any(issue.stage == "E" and issue.status == "unavailable" for issue in snapshot.issues)
    assert any(issue.stage == "R" and issue.status == "pending" for issue in snapshot.issues)

    tracker.mark("C", 500, 1000, "unavailable", modality="video", reason="no track", revision=2)
    assert tracker.snapshot(through_ms=1000).C_ms == 1000


def test_uncovered_hole_holds_cursor_until_explicit_terminal_status() -> None:
    tracker = WatermarkTracker("audio-only", required_modalities={"audio"})
    tracker.mark("C", 0, 400, "done", modality="audio")
    tracker.mark("C", 600, 1000, "done", modality="audio")
    pending = tracker.snapshot(through_ms=1000)
    assert pending.C_ms == 400
    assert any(
        issue.stage == "C"
        and issue.start_ms == 400
        and issue.end_ms == 600
        and issue.status == "pending"
        for issue in pending.issues
    )

    tracker.mark("C", 400, 600, "dropped", modality="audio", reason="ring overflow")
    completed = tracker.snapshot(through_ms=1000)
    assert completed.C_ms == 1000
    assert any(
        issue.status == "dropped" and issue.reason == "ring overflow"
        for issue in completed.issues
    )


def test_revision_overlay_splits_intervals_and_rejects_stale_updates() -> None:
    tracker = WatermarkTracker("stream-1", required_modalities={"audio"})
    tracker.mark("R", 0, 1000, "done", level="L2", revision=1)
    tracker.mark("R", 300, 700, "pending", level="L2", revision=2)
    assert tracker.snapshot(through_ms=1000).R_ms["L2"] == 300
    spans = tracker.spans("R", level="L2")
    assert [(span.start_ms, span.end_ms, span.status) for span in spans] == [
        (0, 300, "done"),
        (300, 700, "pending"),
        (700, 1000, "done"),
    ]
    with pytest.raises(StaleCoverageRevisionError):
        tracker.mark("R", 400, 500, "done", level="L2", revision=1)

    tracker.mark("R", 300, 700, "done", level="L2", revision=3)
    assert tracker.snapshot(through_ms=1000).R_ms["L2"] == 1000
    assert not tracker.mark("R", 300, 700, "done", level="L2", revision=3)


def test_epoch_reset_clears_coverage_and_rejects_late_previous_epoch_update() -> None:
    tracker = WatermarkTracker("stream-1", required_modalities={"audio"})
    tracker.mark("C", 0, 800, "done", modality="audio", epoch=0)
    tracker.begin_epoch(1)
    assert tracker.snapshot(through_ms=800).C_ms == 0
    with pytest.raises(StaleCoverageRevisionError, match="epoch"):
        tracker.mark("C", 800, 1200, "done", modality="audio", epoch=0)


def test_snapshot_exposes_explicit_gap_and_pending_across_unstarted_levels() -> None:
    tracker = WatermarkTracker("stream-1", required_modalities={"audio"})
    tracker.mark("C", 0, 1000, "done", modality="audio")
    tracker.mark("R", 0, 300, "done", level="L3")
    tracker.mark("R", 300, 500, "gap", level="L3", reason="caption skipped")
    snapshot = tracker.snapshot(through_ms=1000)
    values = snapshot.to_dict()
    assert values["C"] == 1000
    assert values["R"]["L3"] == 500  # type: ignore[index]
    assert snapshot.R_ms["L1"] == 0
    assert any(issue.level == "L3" and issue.status == "gap" for issue in snapshot.issues)
    assert any(issue.level == "L1" and issue.status == "pending" for issue in snapshot.issues)


def test_mark_uncovered_preserves_prefetch_drop_coverage() -> None:
    tracker = WatermarkTracker("video-only", required_modalities={"video"})
    tracker.mark("E", 100, 101, "dropped", modality="video", reason="prefetch_queue_full")

    tracker.mark_uncovered(
        "E", 0, 500, "skipped", modality="video", reason="embedding_stride"
    )

    spans = tracker.spans("E", modality="video")
    assert [(span.start_ms, span.end_ms, span.status) for span in spans] == [
        (0, 100, "skipped"),
        (100, 101, "dropped"),
        (101, 500, "skipped"),
    ]


def test_watermark_updates_are_safe_across_producer_threads() -> None:
    tracker = WatermarkTracker("audio-only", required_modalities={"audio"})

    def mark_interval(index: int) -> None:
        start_ms = index * 10
        tracker.mark("C", start_ms, start_ms + 10, "done", modality="audio")
        tracker.snapshot(through_ms=1_000)

    with ThreadPoolExecutor(max_workers=8) as workers:
        list(workers.map(mark_interval, range(100)))

    assert tracker.snapshot(through_ms=1_000).C_ms == 1_000
    assert len(tracker.spans("C", modality="audio")) == 1
