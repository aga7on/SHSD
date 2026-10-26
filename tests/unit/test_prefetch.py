from __future__ import annotations

from collections.abc import Iterator
from threading import Event

import pytest

from shsd.ingest.prefetch import (
    MediaAdmissionTelemetry,
    OverflowPolicy,
    PrefetchTelemetry,
    iter_bounded_prefetch,
    iter_merge_by_key,
)


def test_iter_merge_by_key_interleaves_sorted_modalities() -> None:
    audio = [(0, "audio-0"), (5_000, "audio-5"), (10_000, "audio-10")]
    video = [(1_000, "video-1"), (6_000, "video-6"), (11_000, "video-11")]

    result = list(
        iter_merge_by_key((audio, video), key=lambda item: item[0])
    )

    assert [item[1] for item in result] == [
        "audio-0",
        "video-1",
        "audio-5",
        "video-6",
        "audio-10",
        "video-11",
    ]


def test_iter_merge_by_key_prioritizes_capture_at_equal_readiness() -> None:
    media = [(1_000, "audio", "window"), (2_000, "audio", "window-2")]
    coverage = [(1_000, "video", "capture-drop")]
    telemetry = MediaAdmissionTelemetry(source_count=2)

    result = list(
        iter_merge_by_key(
            (media, coverage),
            key=lambda item: item[0],
            priority=lambda item: 0 if item[2].startswith("capture") else 1,
            telemetry=telemetry,
        )
    )

    assert [item[2] for item in result] == ["capture-drop", "window", "window-2"]
    assert telemetry.to_dict() == {
        "capacity": 2,
        "peak_pending": 2,
        "admitted_count": 3,
        "dispatched_count": 3,
    }


def test_iter_merge_by_key_rejects_non_monotonic_source() -> None:
    merged = iter_merge_by_key(([(2, "later"), (1, "earlier")],), key=lambda item: item[0])

    assert next(merged) == (2, "later")
    with pytest.raises(ValueError, match="not sorted by work-ready key"):
        next(merged)


def test_iter_merge_by_key_closes_sources_when_consumer_stops_early() -> None:
    closed: list[str] = []

    def source(name: str, rows: list[tuple[int, str]]) -> Iterator[tuple[int, str]]:
        try:
            yield from rows
        finally:
            closed.append(name)

    merged = iter_merge_by_key(
        (source("audio", [(0, "a"), (2, "c")]), source("video", [(1, "b")])),
        key=lambda item: item[0],
    )
    assert next(merged) == (0, "a")
    merged.close()

    assert sorted(closed) == ["audio", "video"]


@pytest.mark.parametrize(
    ("policy", "expected_item", "expected_drop"),
    [
        ("drop_newest", "second", "third"),
        ("drop_oldest", "third", "second"),
    ],
)
def test_bounded_prefetch_reports_explicit_overflow_policy(
    policy: OverflowPolicy, expected_item: str, expected_drop: str
) -> None:
    allow_second = Event()
    second_enqueued = Event()
    third_processed = Event()
    telemetry = PrefetchTelemetry(capacity=1)
    dropped: list[tuple[str, str]] = []

    def source() -> Iterator[str]:
        yield "first"
        assert allow_second.wait(timeout=2)
        yield "second"
        second_enqueued.set()
        yield "third"
        third_processed.set()

    rows = iter_bounded_prefetch(
        source,
        telemetry=telemetry,
        overflow_policy=policy,
        on_drop=lambda item, reason: dropped.append((item, reason)),
    )
    try:
        assert next(rows) == "first"
        allow_second.set()
        assert second_enqueued.wait(timeout=2)
        assert third_processed.wait(timeout=2)
        assert next(rows) == expected_item
        with pytest.raises(StopIteration):
            next(rows)
    finally:
        rows.close()

    assert telemetry.overflow_policy == policy
    assert telemetry.peak_depth == 1
    assert telemetry.dropped_count == 1
    assert dropped == [(expected_drop, "prefetch_queue_full")]
