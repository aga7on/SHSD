from __future__ import annotations

import hashlib
import tracemalloc
from pathlib import Path

from shsd.ingest.ring import DroppedChunk, MediaChunk, MediaRing


def test_ring_retains_by_media_time_and_deduplicates_packets(tmp_path: Path) -> None:
    ring = MediaRing(window_ms=60_000, max_memory_bytes=10_000, spill_dir=tmp_path)
    first = ring.append(
        stream_id="stream-a",
        epoch=0,
        start_ms=0,
        end_ms=100,
        kind="audio",
        data=b"a" * 100,
        source_pts_range=(0, 4800),
    )
    repeated = ring.append(
        stream_id="stream-a",
        epoch=0,
        start_ms=0,
        end_ms=100,
        kind="audio",
        data=b"a" * 100,
        source_pts_range=(0, 4800),
    )
    ring.append(
        stream_id="stream-a",
        epoch=0,
        start_ms=59_999,
        end_ms=60_000,
        kind="video",
        data=b"b" * 100,
    )

    assert isinstance(first, MediaChunk)
    assert repeated.chunk_id == first.chunk_id
    assert ring.get(first.chunk_id) is not None

    ring.append(
        stream_id="stream-a",
        epoch=0,
        start_ms=60_101,
        end_ms=60_102,
        kind="video",
        data=b"c" * 100,
    )

    assert ring.get(first.chunk_id) is None
    assert ring.stats.memory_bytes == 200


def test_ring_spills_a_leased_old_chunk_then_removes_it_on_release(tmp_path: Path) -> None:
    ring = MediaRing(
        window_ms=100,
        max_memory_bytes=4,
        spill_dir=tmp_path,
        max_spill_bytes=8,
    )
    first = ring.append(
        stream_id="stream-a",
        epoch=0,
        start_ms=0,
        end_ms=100,
        kind="video",
        data=b"old!",
    )
    assert isinstance(first, MediaChunk)

    with ring.lease(first.chunk_id) as lease:
        current = ring.append(
            stream_id="stream-a",
            epoch=0,
            start_ms=201,
            end_ms=301,
            kind="audio",
            data=b"new!",
        )
        assert isinstance(current, MediaChunk)
        spilled = ring.get(first.chunk_id)
        assert spilled is not None
        assert spilled.storage_ref.endswith(".bin")
        assert ring.stats.spill_bytes == 4
        assert lease.read() == b"old!"

    assert ring.get(first.chunk_id) is None
    assert ring.stats.spill_bytes == 0
    assert ring.stats.memory_bytes == 4


def test_ring_emits_dropped_when_memory_and_spill_limits_are_full() -> None:
    ring = MediaRing(window_ms=1000, max_memory_bytes=4)
    retained = ring.append(
        stream_id="stream-a",
        epoch=0,
        start_ms=0,
        end_ms=10,
        kind="audio",
        data=b"keep",
    )
    dropped = ring.append(
        stream_id="stream-a",
        epoch=0,
        start_ms=10,
        end_ms=20,
        kind="audio",
        data=b"drop",
    )

    assert isinstance(retained, MediaChunk)
    assert isinstance(dropped, DroppedChunk)
    assert dropped.status == "dropped"
    assert dropped.reason == "capacity_limit"
    assert ring.stats.dropped_count == 1
    assert ring.stats.memory_bytes == 4


def test_ring_caps_metadata_count_even_when_payload_budget_has_room() -> None:
    ring = MediaRing(window_ms=1000, max_memory_bytes=100, max_chunks=1)
    first = ring.append(
        stream_id="stream-a",
        epoch=0,
        start_ms=0,
        end_ms=10,
        kind="audio",
        data=b"one",
    )
    second = ring.append(
        stream_id="stream-a",
        epoch=0,
        start_ms=10,
        end_ms=20,
        kind="video",
        data=b"two",
    )

    assert isinstance(first, MediaChunk)
    assert isinstance(second, DroppedChunk)
    assert second.reason == "capacity_limit"
    assert ring.stats.chunk_count == 1


def test_ring_discards_old_epochs_and_rejects_late_stale_packets() -> None:
    ring = MediaRing(window_ms=1000, max_memory_bytes=100)
    old = ring.append(
        stream_id="stream-a",
        epoch=0,
        start_ms=5000,
        end_ms=5010,
        kind="video",
        data=b"old",
    )
    current = ring.append(
        stream_id="stream-a",
        epoch=1,
        start_ms=0,
        end_ms=10,
        kind="video",
        data=b"new",
    )
    stale = ring.append(
        stream_id="stream-a",
        epoch=0,
        start_ms=5010,
        end_ms=5020,
        kind="video",
        data=b"late",
    )

    assert isinstance(old, MediaChunk)
    assert isinstance(current, MediaChunk)
    assert ring.get(old.chunk_id) is None
    assert isinstance(stale, DroppedChunk)
    assert stale.reason == "stale_epoch"
    assert ring.stats.epoch == 1


def test_ring_bounds_memory_over_thirty_minutes_of_media_time() -> None:
    tracemalloc.start()
    ring = MediaRing(window_ms=600_000, max_memory_bytes=1_000_000)
    for second in range(30 * 60):
        ring.append(
            stream_id="stream-a",
            epoch=0,
            start_ms=second * 1000,
            end_ms=(second + 1) * 1000,
            kind="audio",
            data=bytes([second % 256]) * 1024,
        )

    stats = ring.stats
    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert stats.media_end_ms == 1_800_000
    assert stats.memory_bytes <= 1_000_000
    assert stats.chunk_count <= 601
    assert stats.dropped_count == 0
    assert current_bytes < 4 * 1024 * 1024
    assert peak_bytes < 8 * 1024 * 1024


def test_ring_records_content_hash_and_removes_files_on_close(tmp_path: Path) -> None:
    ring = MediaRing(
        max_memory_bytes=0,
        spill_dir=tmp_path,
        max_spill_bytes=100,
    )
    chunk = ring.append(
        stream_id="stream-a",
        epoch=0,
        start_ms=0,
        end_ms=10,
        kind="audio",
        data=b"wave",
    )
    assert isinstance(chunk, MediaChunk)
    assert chunk.content_hash == hashlib.sha256(b"wave").hexdigest()
    assert Path(chunk.storage_ref).read_bytes() == b"wave"

    ring.close()

    assert ring.stats.chunk_count == 0
    assert ring.stats.spill_bytes == 0
    assert list(tmp_path.iterdir()) == []
