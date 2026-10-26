"""Bounded, timestamp-based media ring with leases and disk spill."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import uuid4

ChunkKind = Literal["audio", "video"]
DropReason = Literal["stale_epoch", "outside_window", "capacity_limit"]
RING_WINDOW_MS = 600_000
RING_MEMORY_BYTES = 64 * 1024 * 1024
RING_SPILL_BYTES = 256 * 1024 * 1024
RING_MAX_CHUNKS = 75_000


@dataclass(frozen=True, slots=True)
class MediaChunk:
    """Metadata for one stored compressed media packet."""

    chunk_id: str
    stream_id: str
    epoch: int
    start_ms: int
    end_ms: int
    kind: ChunkKind
    content_hash: str
    storage_ref: str
    source_pts_range: tuple[int, int] | None
    size_bytes: int


@dataclass(frozen=True, slots=True)
class DroppedChunk:
    """Explicit record that a packet could not be retained by the ring."""

    status: Literal["dropped"]
    chunk_id: str
    stream_id: str
    epoch: int
    start_ms: int
    end_ms: int
    kind: ChunkKind
    reason: DropReason
    size_bytes: int


@dataclass(frozen=True, slots=True)
class RingStats:
    chunk_count: int
    memory_bytes: int
    spill_bytes: int
    dropped_count: int
    media_end_ms: int | None
    epoch: int | None


@dataclass(slots=True)
class _StoredChunk:
    metadata: MediaChunk
    data: bytes | None
    spill_path: Path | None
    leases: int = 0


class ChunkLease:
    """Reference-counted handle that keeps a ring chunk readable."""

    def __init__(self, ring: MediaRing, chunk_id: str) -> None:
        self._ring = ring
        self.chunk_id = chunk_id
        self._released = False

    def read(self) -> bytes:
        if self._released:
            raise RuntimeError("lease has already been released")
        return self._ring._read(self.chunk_id)

    def close(self) -> None:
        if not self._released:
            self._ring._release(self.chunk_id)
            self._released = True

    def __enter__(self) -> ChunkLease:
        if self._released:
            raise RuntimeError("lease has already been released")
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()


class MediaRing:
    """Keep a timestamp window with separate in-memory and spill limits.

    Create one ring per stream. An epoch change clears old unleased chunks;
    leased chunks are moved to spill storage when space allows. If neither
    storage budget can hold a new packet, ``append`` returns ``DroppedChunk``.
    """

    def __init__(
        self,
        *,
        window_ms: int = RING_WINDOW_MS,
        max_memory_bytes: int = RING_MEMORY_BYTES,
        max_chunks: int = RING_MAX_CHUNKS,
        spill_dir: str | Path | None = None,
        max_spill_bytes: int = 0,
    ) -> None:
        if window_ms <= 0:
            raise ValueError("window_ms must be positive")
        if max_memory_bytes < 0 or max_spill_bytes < 0:
            raise ValueError("storage limits must be non-negative")
        if max_chunks < 1:
            raise ValueError("max_chunks must be positive")
        if max_spill_bytes and spill_dir is None:
            raise ValueError("spill_dir is required when max_spill_bytes is non-zero")
        self.window_ms = window_ms
        self.max_memory_bytes = max_memory_bytes
        self.max_chunks = max_chunks
        self.spill_dir = (
            Path(spill_dir) / f"ring-{uuid4().hex}" if spill_dir is not None else None
        )
        self.max_spill_bytes = max_spill_bytes
        self._chunks: dict[str, _StoredChunk] = {}
        self._memory_bytes = 0
        self._spill_bytes = 0
        self._dropped_count = 0
        self._stream_id: str | None = None
        self._epoch: int | None = None
        self._media_end_ms: int | None = None
        self._closed = False
        self._lock = RLock()

    @property
    def stats(self) -> RingStats:
        with self._lock:
            return RingStats(
                chunk_count=len(self._chunks),
                memory_bytes=self._memory_bytes,
                spill_bytes=self._spill_bytes,
                dropped_count=self._dropped_count,
                media_end_ms=self._media_end_ms,
                epoch=self._epoch,
            )

    def snapshot(self) -> tuple[MediaChunk, ...]:
        """Return current chunk metadata in media-time order."""
        with self._lock:
            chunks = (chunk.metadata for chunk in self._chunks.values())
            return tuple(
                sorted(
                    chunks,
                    key=lambda chunk: (
                        chunk.epoch,
                        chunk.start_ms,
                        chunk.kind,
                        chunk.chunk_id,
                    ),
                )
            )

    def get(self, chunk_id: str) -> MediaChunk | None:
        with self._lock:
            stored = self._chunks.get(chunk_id)
            return stored.metadata if stored is not None else None

    def append(
        self,
        *,
        stream_id: str,
        epoch: int,
        start_ms: int,
        end_ms: int,
        kind: ChunkKind,
        data: bytes,
        source_pts_range: tuple[int, int] | None = None,
    ) -> MediaChunk | DroppedChunk:
        """Append one packet or return its explicit drop event."""
        if self._closed:
            raise RuntimeError("ring is closed")
        if not stream_id:
            raise ValueError("stream_id must not be empty")
        if epoch < 0:
            raise ValueError("epoch must be non-negative")
        if start_ms > end_ms:
            raise ValueError("chunk interval must satisfy start_ms <= end_ms")
        if not data:
            raise ValueError("chunk data must not be empty")
        if source_pts_range is not None and source_pts_range[0] > source_pts_range[1]:
            raise ValueError("source_pts_range must be ordered")

        content_hash = hashlib.sha256(data).hexdigest()
        identity = "\0".join(
            [
                stream_id,
                str(epoch),
                str(start_ms),
                str(end_ms),
                kind,
                content_hash,
                str(source_pts_range),
            ]
        )
        chunk_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()

        with self._lock:
            if self._closed:
                raise RuntimeError("ring is closed")
            if self._stream_id is None:
                self._stream_id = stream_id
            elif self._stream_id != stream_id:
                raise ValueError("a MediaRing can contain only one stream_id")
            if self._epoch is not None and epoch < self._epoch:
                return self._drop(
                    chunk_id, stream_id, epoch, start_ms, end_ms, kind, "stale_epoch", len(data)
                )

            existing = self._chunks.get(chunk_id)
            if existing is not None:
                return existing.metadata

            if self._epoch is None or epoch > self._epoch:
                self._epoch = epoch
                self._media_end_ms = end_ms
            else:
                assert self._media_end_ms is not None
                self._media_end_ms = max(self._media_end_ms, end_ms)
            self._prune()

            cutoff = self._media_end_ms - self.window_ms
            if end_ms < cutoff:
                return self._drop(
                    chunk_id,
                    stream_id,
                    epoch,
                    start_ms,
                    end_ms,
                    kind,
                    "outside_window",
                    len(data),
                )
            if len(self._chunks) >= self.max_chunks:
                return self._drop(
                    chunk_id,
                    stream_id,
                    epoch,
                    start_ms,
                    end_ms,
                    kind,
                    "capacity_limit",
                    len(data),
                )

            metadata = MediaChunk(
                chunk_id=chunk_id,
                stream_id=stream_id,
                epoch=epoch,
                start_ms=start_ms,
                end_ms=end_ms,
                kind=kind,
                content_hash=content_hash,
                storage_ref="",
                source_pts_range=source_pts_range,
                size_bytes=len(data),
            )
            stored = _StoredChunk(metadata=metadata, data=None, spill_path=None)
            if len(data) <= self.max_memory_bytes and self._make_room(len(data)):
                stored.data = data
                stored.metadata = replace(metadata, storage_ref=f"memory:{chunk_id}")
                self._memory_bytes += len(data)
            elif not self._write_spill(stored, data):
                return self._drop(
                    chunk_id,
                    stream_id,
                    epoch,
                    start_ms,
                    end_ms,
                    kind,
                    "capacity_limit",
                    len(data),
                )
            self._chunks[chunk_id] = stored
            self._prune()
            return stored.metadata

    def lease(self, chunk_id: str) -> ChunkLease:
        """Acquire a chunk so timestamp eviction cannot destroy it mid-task."""
        with self._lock:
            stored = self._chunks.get(chunk_id)
            if stored is None:
                raise KeyError(f"media chunk not found: {chunk_id}")
            stored.leases += 1
            return ChunkLease(self, chunk_id)

    def close(self) -> None:
        """Reject new chunks and remove all unleased storage."""
        with self._lock:
            self._closed = True
            self._prune()
            self._cleanup_spill_directory()

    def _make_room(self, incoming_bytes: int) -> bool:
        candidates = sorted(
            (chunk for chunk in self._chunks.values() if chunk.data is not None),
            key=lambda chunk: (chunk.metadata.epoch, chunk.metadata.start_ms),
        )
        for stored in candidates:
            if self._memory_bytes + incoming_bytes <= self.max_memory_bytes:
                break
            if stored.data is not None:
                self._write_spill(stored, stored.data)
        return self._memory_bytes + incoming_bytes <= self.max_memory_bytes

    def _write_spill(self, stored: _StoredChunk, data: bytes) -> bool:
        if self.spill_dir is None or len(data) + self._spill_bytes > self.max_spill_bytes:
            return False
        self.spill_dir.mkdir(parents=True, exist_ok=True)
        spill_path = self.spill_dir / f"{stored.metadata.chunk_id}.bin"
        temporary_path = self.spill_dir / f"{stored.metadata.chunk_id}.tmp"
        try:
            with temporary_path.open("wb") as target:
                target.write(data)
            os.replace(temporary_path, spill_path)
        except OSError:
            temporary_path.unlink(missing_ok=True)
            return False
        was_in_memory = stored.data is not None
        stored.data = None
        stored.spill_path = spill_path
        stored.metadata = replace(stored.metadata, storage_ref=str(spill_path))
        if was_in_memory:
            self._memory_bytes -= len(data)
        self._spill_bytes += len(data)
        return True

    def _is_expired(self, chunk: _StoredChunk) -> bool:
        if self._closed:
            return True
        if self._epoch is None or chunk.metadata.epoch != self._epoch:
            return True
        assert self._media_end_ms is not None
        cutoff = self._media_end_ms - self.window_ms
        return chunk.metadata.end_ms < cutoff

    def _prune(self) -> None:
        for chunk_id, stored in tuple(self._chunks.items()):
            if not self._is_expired(stored):
                continue
            if stored.leases:
                if stored.data is not None:
                    self._write_spill(stored, stored.data)
                continue
            self._remove(chunk_id, stored)

    def _remove(self, chunk_id: str, stored: _StoredChunk) -> None:
        if stored.data is not None:
            self._memory_bytes -= len(stored.data)
        if stored.spill_path is not None:
            stored.spill_path.unlink(missing_ok=True)
            self._spill_bytes -= stored.metadata.size_bytes
        del self._chunks[chunk_id]

    def _read(self, chunk_id: str) -> bytes:
        with self._lock:
            stored = self._chunks.get(chunk_id)
            if stored is None:
                raise KeyError(f"media chunk not found: {chunk_id}")
            if stored.data is not None:
                return stored.data
            if stored.spill_path is None:
                raise RuntimeError(f"media chunk has no storage: {chunk_id}")
            return stored.spill_path.read_bytes()

    def _release(self, chunk_id: str) -> None:
        with self._lock:
            stored = self._chunks.get(chunk_id)
            if stored is None or stored.leases < 1:
                raise RuntimeError(f"media chunk lease underflow: {chunk_id}")
            stored.leases -= 1
            self._prune()
            self._cleanup_spill_directory()

    def _cleanup_spill_directory(self) -> None:
        if self._closed and not self._chunks and self.spill_dir is not None:
            try:
                self.spill_dir.rmdir()
            except OSError:
                pass

    def _drop(
        self,
        chunk_id: str,
        stream_id: str,
        epoch: int,
        start_ms: int,
        end_ms: int,
        kind: ChunkKind,
        reason: DropReason,
        size_bytes: int,
    ) -> DroppedChunk:
        self._dropped_count += 1
        return DroppedChunk(
            status="dropped",
            chunk_id=chunk_id,
            stream_id=stream_id,
            epoch=epoch,
            start_ms=start_ms,
            end_ms=end_ms,
            kind=kind,
            reason=reason,
            size_bytes=size_bytes,
        )


def default_spill_directory() -> Path:
    """Return a local temporary directory for a process-scoped ring."""
    return Path(tempfile.gettempdir()) / "shsd-media-ring"
