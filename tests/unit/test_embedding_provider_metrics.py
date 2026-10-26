from __future__ import annotations

import threading
import time
from contextlib import nullcontext
from typing import Any

import numpy as np

from shsd.embeddings.provider import EMBEDDING_DIM, EmbeddingProvider, _FairLock


def test_model_latency_excludes_wait_for_shared_inference_lock() -> None:
    class FakeEncoder:
        def encode(self, _inputs: object, **_kwargs: Any) -> np.ndarray:
            time.sleep(0.02)
            return np.zeros((1, EMBEDDING_DIM), dtype=np.float32)

    provider = EmbeddingProvider.__new__(EmbeddingProvider)
    provider._inference_lock = threading.Lock()
    provider._torch = type("TorchStub", (), {"inference_mode": staticmethod(nullcontext)})()
    provider.encoder = FakeEncoder()
    provider._inference_lock.acquire()
    entered = threading.Event()
    result: dict[str, float] = {}

    def encode() -> None:
        entered.set()
        _vectors, latency_ms = provider._encode_missing("fixture", 1)
        result["latency_ms"] = latency_ms

    worker = threading.Thread(target=encode)
    started = time.perf_counter()
    worker.start()
    try:
        assert entered.wait(timeout=1)
        time.sleep(0.15)
    finally:
        provider._inference_lock.release()
    worker.join(timeout=2)

    elapsed_ms = (time.perf_counter() - started) * 1000
    assert not worker.is_alive()
    assert elapsed_ms >= 120
    assert 0 < result["latency_ms"] < 100


def test_shared_inference_lock_serves_waiting_streams_fifo() -> None:
    lock = _FairLock()
    lock.acquire()
    service_order: list[int] = []
    workers: list[threading.Thread] = []

    for stream_index in range(5):
        started = threading.Event()

        def request(index: int = stream_index, entered: threading.Event = started) -> None:
            entered.set()
            with lock:
                service_order.append(index)

        worker = threading.Thread(target=request)
        worker.start()
        workers.append(worker)
        assert started.wait(timeout=1)
        deadline = time.monotonic() + 1
        while lock.waiting_count < stream_index + 1 and time.monotonic() < deadline:
            time.sleep(0.001)
        assert lock.waiting_count == stream_index + 1

    assert not lock.acquire(blocking=False)
    lock.release()
    for worker in workers:
        worker.join(timeout=1)

    assert all(not worker.is_alive() for worker in workers)
    assert service_order == list(range(5))
