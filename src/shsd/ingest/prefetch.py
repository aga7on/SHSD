"""Bounded producer/consumer prefetch for decoded media work items."""

from __future__ import annotations

from collections.abc import Callable, Generator, Iterable, Iterator
from dataclasses import dataclass
from heapq import heappop, heappush
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from time import monotonic
from typing import Literal, TypeVar, cast

T = TypeVar("T")
_MessageKind = Literal["item", "error", "end"]
OverflowPolicy = Literal["block", "drop_newest", "drop_oldest"]


@dataclass(slots=True)
class PrefetchTelemetry:
    """Queue bounds and producer stalls observed during one analysis pass."""

    capacity: int
    overflow_policy: OverflowPolicy = "block"
    produced_count: int = 0
    current_depth: int = 0
    peak_depth: int = 0
    producer_block_count: int = 0
    producer_block_ms: float = 0.0
    dropped_count: int = 0

    def to_dict(self) -> dict[str, int | float | str]:
        return {
            "capacity": self.capacity,
            "overflow_policy": self.overflow_policy,
            "produced_count": self.produced_count,
            "current_depth": self.current_depth,
            "peak_depth": self.peak_depth,
            "producer_block_count": self.producer_block_count,
            "producer_block_ms": round(self.producer_block_ms, 3),
            "dropped_count": self.dropped_count,
        }


@dataclass(slots=True)
class MediaAdmissionTelemetry:
    """Bounds and counts for the shared one-lookahead-per-source scheduler."""

    source_count: int
    peak_pending: int = 0
    admitted_count: int = 0
    dispatched_count: int = 0

    def __post_init__(self) -> None:
        if self.source_count < 0:
            raise ValueError("source_count must be non-negative")

    def to_dict(self) -> dict[str, int]:
        return {
            "capacity": self.source_count,
            "peak_pending": self.peak_pending,
            "admitted_count": self.admitted_count,
            "dispatched_count": self.dispatched_count,
        }


def iter_bounded_prefetch(
    factory: Callable[[], Iterable[T]],
    *,
    telemetry: PrefetchTelemetry,
    overflow_policy: OverflowPolicy = "block",
    on_drop: Callable[[T, str], None] | None = None,
) -> Generator[T, None, None]:
    """Run ``factory`` on a producer thread with a strictly bounded queue.

    Producer exceptions are re-raised in the consumer. Closing the consumer
    stops further queue writes and lets the producer unwind its media source.
    Callers can select an explicit non-blocking drop policy and observe every
    discarded item through ``on_drop`` (which runs on the producer thread);
    file analysis defaults to block.
    """
    if telemetry.capacity < 1:
        raise ValueError("prefetch capacity must be positive")
    if overflow_policy not in {"block", "drop_newest", "drop_oldest"}:
        raise ValueError("overflow_policy must be block, drop_newest, or drop_oldest")
    telemetry.overflow_policy = overflow_policy

    messages: Queue[tuple[_MessageKind, object | None]] = Queue(
        maxsize=telemetry.capacity
    )
    stop = Event()
    drop_lock = Lock()

    def record_drop(payload: object, reason: str = "prefetch_queue_full") -> None:
        with drop_lock:
            telemetry.dropped_count += 1
            if on_drop is not None:
                on_drop(cast(T, payload), reason)

    def offer_control(kind: Literal["error", "end"], payload: object | None) -> bool:
        while not stop.is_set():
            try:
                messages.put((kind, payload), timeout=0.05)
                telemetry.current_depth = messages.qsize()
                telemetry.peak_depth = max(telemetry.peak_depth, telemetry.current_depth)
                return True
            except Full:
                continue
        return False

    def offer_item(payload: object) -> bool:
        if overflow_policy == "block":
            blocked_at: float | None = None
            while not stop.is_set():
                try:
                    messages.put(("item", payload), timeout=0.05)
                    if blocked_at is not None:
                        telemetry.producer_block_ms += (monotonic() - blocked_at) * 1000
                    telemetry.current_depth = messages.qsize()
                    telemetry.peak_depth = max(telemetry.peak_depth, telemetry.current_depth)
                    telemetry.produced_count += 1
                    return True
                except Full:
                    if blocked_at is None:
                        blocked_at = monotonic()
                        telemetry.producer_block_count += 1
            if blocked_at is not None:
                telemetry.producer_block_ms += (monotonic() - blocked_at) * 1000
            return False

        while not stop.is_set():
            try:
                messages.put_nowait(("item", payload))
                telemetry.current_depth = messages.qsize()
                telemetry.peak_depth = max(telemetry.peak_depth, telemetry.current_depth)
                telemetry.produced_count += 1
                return True
            except Full:
                if overflow_policy == "drop_newest":
                    record_drop(payload)
                    return True
                try:
                    dropped_kind, dropped_payload = messages.get_nowait()
                    telemetry.current_depth = messages.qsize()
                except Empty:
                    continue
                if dropped_kind == "item":
                    record_drop(dropped_payload)
                else:
                    # Control messages are never evicted by a data overflow.
                    messages.put_nowait((dropped_kind, dropped_payload))
                    telemetry.current_depth = messages.qsize()
                    continue
        return False

    def offer(kind: _MessageKind, payload: object | None) -> bool:
        if kind == "item":
            return offer_item(payload)
        return offer_control(kind, payload)

    def produce() -> None:
        try:
            for item in factory():
                if not offer("item", item):
                    return
        except BaseException as error:
            offer_control("error", error)
        finally:
            offer_control("end", None)

    worker = Thread(target=produce, name="shsd-media-prefetch", daemon=True)
    worker.start()
    try:
        while True:
            kind, payload = messages.get()
            telemetry.current_depth = messages.qsize()
            if kind == "end":
                return
            if kind == "error":
                if isinstance(payload, BaseException):
                    raise payload
                raise RuntimeError("prefetch producer failed without an exception")
            yield cast(T, payload)
    finally:
        stop.set()
        worker.join(timeout=4.0)
        while True:
            try:
                kind, payload = messages.get_nowait()
                telemetry.current_depth = messages.qsize()
            except Empty:
                break
            if kind == "item":
                record_drop(payload, "prefetch_cancelled")
        telemetry.current_depth = messages.qsize()


def iter_merge_by_key(
    sources: Iterable[Iterable[T]],
    *,
    key: Callable[[T], int],
    priority: Callable[[T], int] | None = None,
    telemetry: MediaAdmissionTelemetry | None = None,
) -> Iterator[T]:
    """Admit key-sorted work by readiness, then priority, with bounded lookahead.

    At most one item per source is pending. Lower ``priority`` values dispatch
    first when ready times tie; source order breaks any remaining ties.
    """
    iterators = [iter(source) for source in sources]
    if telemetry is not None and telemetry.source_count != len(iterators):
        raise ValueError("telemetry source_count must match the number of sources")
    previous_keys: list[int | None] = [None] * len(iterators)
    pending: list[tuple[int, int, int, T]] = []

    def admit(source_index: int, item: T) -> None:
        item_key = key(item)
        previous_key = previous_keys[source_index]
        if previous_key is not None and item_key < previous_key:
            raise ValueError(
                f"source {source_index} is not sorted by work-ready key: "
                f"{item_key} follows {previous_key}"
            )
        previous_keys[source_index] = item_key
        item_priority = priority(item) if priority is not None else 0
        heappush(pending, (item_key, item_priority, source_index, item))
        if telemetry is not None:
            telemetry.admitted_count += 1
            telemetry.peak_pending = max(telemetry.peak_pending, len(pending))

    try:
        for source_index, iterator in enumerate(iterators):
            try:
                item = next(iterator)
            except StopIteration:
                continue
            admit(source_index, item)

        while pending:
            _, _, source_index, item = heappop(pending)
            if telemetry is not None:
                telemetry.dispatched_count += 1
            yield item
            try:
                following = next(iterators[source_index])
            except StopIteration:
                continue
            admit(source_index, following)
    finally:
        for iterator in iterators:
            close = getattr(iterator, "close", None)
            if callable(close):
                close()
