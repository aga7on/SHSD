from __future__ import annotations

import threading

import pytest

from shsd.workers.l1_worker import BoundedL1Worker, L1Work
from shsd.workers.scheduler import LoadSample, RuntimeLoadController


def test_l1_worker_preserves_order_and_bounds_outstanding() -> None:
    worker = BoundedL1Worker(queue_capacity=2)
    first_started = threading.Event()
    release_first = threading.Event()
    third_attempting = threading.Event()
    order: list[int] = []

    def first() -> None:
        first_started.set()
        assert release_first.wait(timeout=2)
        order.append(1)

    worker.submit(L1Work(job_id=1, run=first))
    assert first_started.wait(timeout=2)
    worker.submit(L1Work(job_id=2, run=lambda: order.append(2)))

    def submit_third() -> None:
        third_attempting.set()
        worker.submit(L1Work(job_id=3, run=lambda: order.append(3)))

    producer = threading.Thread(target=submit_third)
    producer.start()
    try:
        assert third_attempting.wait(timeout=2)
        assert worker.outstanding == 2
        assert producer.is_alive()
    finally:
        release_first.set()
    producer.join(timeout=2)
    assert not producer.is_alive()

    worker.finish()
    snapshot = worker.snapshot()
    assert order == [1, 2, 3]
    assert snapshot["max_outstanding"] == 2
    assert snapshot["completed"] == 3
    assert snapshot["outstanding"] == 0


def test_l1_worker_drains_queue_and_surfaces_first_error() -> None:
    worker = BoundedL1Worker(queue_capacity=2)
    completed: list[int] = []

    def fail() -> None:
        raise ValueError("bad L1 result")

    worker.submit(L1Work(job_id=7, run=fail))
    worker.submit(L1Work(job_id=8, run=lambda: completed.append(8)))

    with pytest.raises(RuntimeError, match="L1 job 7 failed: ValueError: bad L1 result"):
        worker.finish()

    assert completed == [8]
    snapshot = worker.snapshot()
    assert snapshot["failed"] == 1
    assert snapshot["completed"] == 1
    assert snapshot["outstanding"] == 0


def test_l1_worker_uses_shared_admission_and_stays_eligible_when_critical() -> None:
    controller = RuntimeLoadController()
    controller.observe(LoadSample(queue_depth=96, queue_capacity=100))
    completed: list[int] = []
    worker = BoundedL1Worker(queue_capacity=1, load_controller=controller)

    worker.submit(L1Work(job_id=1, run=lambda: completed.append(1)))
    worker.finish()

    assert completed == [1]
    assert controller.status.mode.value == "critical"
