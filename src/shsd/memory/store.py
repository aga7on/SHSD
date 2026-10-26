"""SQLite WAL event journal with compare-and-swap revision writes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Self

from shsd.memory.models import TimelineEvent


class StaleRevisionError(RuntimeError):
    """An asynchronous worker tried to replace a newer timeline revision."""


class EventStore:
    """Append-only event revisions with a compare-and-swap current snapshot."""

    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # All database access is serialized by _lock; L1 workers may share this connection.
        self.connection = sqlite3.connect(
            str(path),
            timeout=30,
            isolation_level=None,
            check_same_thread=False,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 30000")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self._lock = threading.RLock()
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS event_revisions (
                stream_id TEXT NOT NULL,
                epoch INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                event_json TEXT NOT NULL,
                PRIMARY KEY (stream_id, epoch, event_id, revision)
            );
            CREATE TABLE IF NOT EXISTS event_current (
                stream_id TEXT NOT NULL,
                epoch INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                event_json TEXT NOT NULL,
                PRIMARY KEY (stream_id, epoch, event_id)
            );
            CREATE TABLE IF NOT EXISTS stream_epochs (
                stream_id TEXT PRIMARY KEY,
                current_epoch INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS caption_records (
                stream_id TEXT NOT NULL,
                epoch INTEGER NOT NULL,
                caption_id TEXT NOT NULL,
                start_ms INTEGER NOT NULL,
                end_ms INTEGER NOT NULL,
                caption_json TEXT NOT NULL,
                PRIMARY KEY (stream_id, epoch, caption_id)
            );
            CREATE INDEX IF NOT EXISTS caption_records_by_time
                ON caption_records (stream_id, epoch, start_ms, end_ms);
            CREATE TABLE IF NOT EXISTS speech_segment_revisions (
                stream_id TEXT NOT NULL,
                epoch INTEGER NOT NULL,
                segment_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                segment_json TEXT NOT NULL,
                PRIMARY KEY (stream_id, epoch, segment_id, revision)
            );
            CREATE TABLE IF NOT EXISTS speech_segment_current (
                stream_id TEXT NOT NULL,
                epoch INTEGER NOT NULL,
                segment_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                start_ms INTEGER NOT NULL,
                end_ms INTEGER NOT NULL,
                segment_json TEXT NOT NULL,
                PRIMARY KEY (stream_id, epoch, segment_id)
            );
            CREATE INDEX IF NOT EXISTS speech_segments_by_time
                ON speech_segment_current (stream_id, epoch, start_ms, end_ms);
            CREATE TABLE IF NOT EXISTS stream_metadata (
                stream_id TEXT PRIMARY KEY,
                metadata_json TEXT NOT NULL
            );
            """
        )

    def append_caption(self, stream_id: str, epoch: int, caption: dict[str, object]) -> bool:
        """Persist a caption once by content hash so replay is safe to retry."""
        time_range = caption.get("time_range")
        if (
            not stream_id
            or epoch < 0
            or not isinstance(time_range, dict)
            or type(time_range.get("start_ms")) is not int
            or type(time_range.get("end_ms")) is not int
            or time_range["start_ms"] < 0
            or time_range["end_ms"] <= time_range["start_ms"]
            or not isinstance(caption.get("caption_ru"), str)
        ):
            raise ValueError("caption must contain a valid interval and caption_ru")
        caption_json = json.dumps(
            caption, ensure_ascii=False, sort_keys=True, allow_nan=False
        )
        caption_id = hashlib.sha256(caption_json.encode("utf-8")).hexdigest()
        with self._lock:
            cursor = self.connection.execute(
                "INSERT OR IGNORE INTO caption_records "
                "(stream_id, epoch, caption_id, start_ms, end_ms, caption_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    stream_id,
                    epoch,
                    caption_id,
                    time_range["start_ms"],
                    time_range["end_ms"],
                    caption_json,
                ),
            )
        return cursor.rowcount == 1

    def captions(self, stream_id: str, epoch: int) -> tuple[dict[str, object], ...]:
        """Return persisted captions in media-time order."""
        with self._lock:
            rows = self.connection.execute(
                "SELECT caption_json FROM caption_records "
                "WHERE stream_id = ? AND epoch = ? ORDER BY start_ms, end_ms, caption_id",
                (stream_id, epoch),
            ).fetchall()
        return tuple(json.loads(row["caption_json"]) for row in rows)

    def append_speech_segment(
        self, stream_id: str, epoch: int, segment: dict[str, object]
    ) -> None:
        """Persist a speech segment revision with compare-and-swap semantics."""
        segment_id = segment.get("segment_id")
        revision = segment.get("revision")
        start_ms = segment.get("start_ms")
        end_ms = segment.get("end_ms")
        status = segment.get("status")
        if (
            not stream_id
            or epoch < 0
            or not isinstance(segment_id, str)
            or not segment_id
            or type(revision) is not int
            or revision < 1
            or type(start_ms) is not int
            or type(end_ms) is not int
            or start_ms < 0
            or end_ms <= start_ms
            or status not in {"partial", "final", "failed", "dropped"}
        ):
            raise ValueError("speech segment must have an ID, interval, revision, and status")
        segment_json = json.dumps(segment, ensure_ascii=False, sort_keys=True, allow_nan=False)
        identity = (stream_id, epoch, segment_id)
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                row = self.connection.execute(
                    "SELECT revision FROM speech_segment_current "
                    "WHERE stream_id = ? AND epoch = ? AND segment_id = ?",
                    identity,
                ).fetchone()
                current_revision = int(row["revision"]) if row else 0
                if revision != current_revision + 1:
                    raise StaleRevisionError(
                        f"stale speech segment revision: expected {current_revision + 1}, "
                        f"received {revision} for {identity}"
                    )
                if current_revision > 0 and segment.get("supersedes_revision") != current_revision:
                    raise ValueError(
                        "speech segment supersedes_revision must match current revision"
                    )
                if current_revision == 0 and segment.get("supersedes_revision") is not None:
                    raise ValueError("new speech segment cannot supersede a prior revision")
                self.connection.execute(
                    "INSERT INTO speech_segment_revisions "
                    "(stream_id, epoch, segment_id, revision, segment_json) VALUES (?, ?, ?, ?, ?)",
                    (*identity, revision, segment_json),
                )
                self.connection.execute(
                    "INSERT INTO speech_segment_current "
                    "(stream_id, epoch, segment_id, revision, start_ms, end_ms, segment_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(stream_id, epoch, segment_id) "
                    "DO UPDATE SET revision = excluded.revision, start_ms = excluded.start_ms, "
                    "end_ms = excluded.end_ms, segment_json = excluded.segment_json",
                    (*identity, revision, start_ms, end_ms, segment_json),
                )
                self.connection.execute("COMMIT")
            except Exception:
                self.connection.execute("ROLLBACK")
                raise

    def speech_segments(
        self,
        stream_id: str,
        epoch: int,
        *,
        from_ms: int | None = None,
        to_ms: int | None = None,
        limit: int = 1_000,
    ) -> tuple[dict[str, object], ...]:
        """Return current timestamp-ordered speech segment revisions."""
        if limit < 1 or limit > 10_000:
            raise ValueError("speech segment limit must be between 1 and 10000")
        conditions = ["stream_id = ?", "epoch = ?"]
        params: list[object] = [stream_id, epoch]
        if from_ms is not None:
            conditions.append("end_ms > ?")
            params.append(from_ms)
        if to_ms is not None:
            conditions.append("start_ms < ?")
            params.append(to_ms)
        params.append(limit)
        with self._lock:
            rows = self.connection.execute(
                "SELECT segment_json FROM speech_segment_current "
                f"WHERE {' AND '.join(conditions)} "
                "ORDER BY start_ms, end_ms, segment_id LIMIT ?",
                params,
            ).fetchall()
        return tuple(json.loads(row["segment_json"]) for row in rows)

    def save_stream_metadata(self, stream_id: str, metadata: dict[str, object]) -> None:
        """Store the local stream descriptor needed to reopen an event journal."""
        if not stream_id:
            raise ValueError("stream_id must be non-empty")
        metadata_json = json.dumps(
            metadata, ensure_ascii=False, sort_keys=True, allow_nan=False
        )
        with self._lock:
            self.connection.execute(
                "INSERT INTO stream_metadata (stream_id, metadata_json) VALUES (?, ?) "
                "ON CONFLICT(stream_id) DO UPDATE SET metadata_json = excluded.metadata_json",
                (stream_id, metadata_json),
            )

    def load_stream_metadata(self, stream_id: str) -> dict[str, object] | None:
        """Read the persisted descriptor for a stream, if one is present."""
        with self._lock:
            row = self.connection.execute(
                "SELECT metadata_json FROM stream_metadata WHERE stream_id = ?",
                (stream_id,),
            ).fetchone()
        if row is None:
            return None
        value = json.loads(row["metadata_json"])
        return value if isinstance(value, dict) else None

    def begin_epoch(self, stream_id: str, epoch: int) -> None:
        """Advance a stream after a seek/reconnect and reject stale worker results."""
        if not stream_id or epoch < 0:
            raise ValueError("stream_id must be non-empty and epoch must be non-negative")
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                row = self.connection.execute(
                    "SELECT current_epoch FROM stream_epochs WHERE stream_id = ?",
                    (stream_id,),
                ).fetchone()
                if row is None:
                    self.connection.execute(
                        "INSERT INTO stream_epochs (stream_id, current_epoch) VALUES (?, ?)",
                        (stream_id, epoch),
                    )
                else:
                    current_epoch = int(row["current_epoch"])
                    if epoch < current_epoch:
                        raise ValueError(
                            f"epoch cannot move backwards from {current_epoch} to {epoch}"
                        )
                    if epoch > current_epoch:
                        self.connection.execute(
                            "UPDATE stream_epochs SET current_epoch = ? WHERE stream_id = ?",
                            (epoch, stream_id),
                        )
                self.connection.execute("COMMIT")
            except Exception:
                self.connection.execute("ROLLBACK")
                raise

    def append(self, event: TimelineEvent, *, expected_revision: int) -> None:
        """Append exactly the next revision if the writer's expected head is current."""
        if expected_revision < 0 or event.revision != expected_revision + 1:
            raise ValueError("event revision must be expected_revision + 1")
        if expected_revision == 0 and event.supersedes_revision is not None:
            raise ValueError("a new event cannot supersede a previous revision")
        if expected_revision > 0 and event.supersedes_revision != expected_revision:
            raise ValueError("event supersedes_revision must match expected_revision")
        event_json = json.dumps(
            event.to_dict(), ensure_ascii=False, sort_keys=True, allow_nan=False
        )
        identity = (event.stream_id, event.epoch, event.event_id)
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                epoch_row = self.connection.execute(
                    "SELECT current_epoch FROM stream_epochs WHERE stream_id = ?",
                    (event.stream_id,),
                ).fetchone()
                if epoch_row is None:
                    self.connection.execute(
                        "INSERT INTO stream_epochs (stream_id, current_epoch) VALUES (?, ?)",
                        (event.stream_id, event.epoch),
                    )
                elif int(epoch_row["current_epoch"]) != event.epoch:
                    raise StaleRevisionError(
                        f"stale event epoch {event.epoch}; current epoch is "
                        f"{int(epoch_row['current_epoch'])} for {event.stream_id}"
                    )
                row = self.connection.execute(
                    "SELECT revision FROM event_current "
                    "WHERE stream_id = ? AND epoch = ? AND event_id = ?",
                    identity,
                ).fetchone()
                current_revision = int(row["revision"]) if row else 0
                if current_revision != expected_revision:
                    raise StaleRevisionError(
                        f"stale event revision: expected current {expected_revision}, "
                        f"found {current_revision} for {identity}"
                    )
                self.connection.execute(
                    "INSERT INTO event_revisions "
                    "(stream_id, epoch, event_id, revision, event_json) VALUES (?, ?, ?, ?, ?)",
                    (*identity, event.revision, event_json),
                )
                self.connection.execute(
                    "INSERT INTO event_current "
                    "(stream_id, epoch, event_id, revision, event_json) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(stream_id, epoch, event_id) DO UPDATE SET "
                    "revision = excluded.revision, event_json = excluded.event_json",
                    (*identity, event.revision, event_json),
                )
                self.connection.execute("COMMIT")
            except Exception:
                self.connection.execute("ROLLBACK")
                raise

    def current(self, stream_id: str, epoch: int, event_id: str) -> TimelineEvent | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT event_json FROM event_current "
                "WHERE stream_id = ? AND epoch = ? AND event_id = ?",
                (stream_id, epoch, event_id),
            ).fetchone()
        if row is None:
            return None
        return TimelineEvent.from_dict(json.loads(row["event_json"]))

    def history(self, stream_id: str, epoch: int, event_id: str) -> tuple[TimelineEvent, ...]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT event_json FROM event_revisions "
                "WHERE stream_id = ? AND epoch = ? AND event_id = ? ORDER BY revision",
                (stream_id, epoch, event_id),
            ).fetchall()
        return tuple(TimelineEvent.from_dict(json.loads(row["event_json"])) for row in rows)

    def current_events(self, stream_id: str, epoch: int) -> tuple[TimelineEvent, ...]:
        """Return the latest event revision for each event in a stream epoch."""
        with self._lock:
            rows = self.connection.execute(
                "SELECT event_json FROM event_current "
                "WHERE stream_id = ? AND epoch = ? ORDER BY event_id",
                (stream_id, epoch),
            ).fetchall()
        return tuple(TimelineEvent.from_dict(json.loads(row["event_json"])) for row in rows)

    def all_revisions(self, stream_id: str, epoch: int) -> tuple[TimelineEvent, ...]:
        """Return every append-only event revision in a stream epoch."""
        with self._lock:
            rows = self.connection.execute(
                "SELECT event_json FROM event_revisions "
                "WHERE stream_id = ? AND epoch = ? "
                "ORDER BY event_id, revision",
                (stream_id, epoch),
            ).fetchall()
        return tuple(TimelineEvent.from_dict(json.loads(row["event_json"])) for row in rows)

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
