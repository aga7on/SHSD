from __future__ import annotations

from threading import Event, Lock

import numpy as np

from shsd.embeddings.provider import EmbeddingRecord
from shsd.workers.embedding_worker import (
    BoundedEmbeddingWorker,
    EmbeddingJob,
    EmbeddingResult,
    SharedEmbeddingDispatcher,
)
from shsd.workers.scheduler import LoadMode, LoadSample, RuntimeLoadController


def test_embedding_lane_uses_shared_admission_and_stays_eligible_when_critical() -> None:
    controller = RuntimeLoadController()
    controller.observe(LoadSample(queue_depth=96, queue_capacity=100))
    worker = BoundedEmbeddingWorker(queue_capacity=1, load_controller=controller)
    record = EmbeddingRecord(
        embedding=np.ones(1, dtype=np.float32),
        model_revision="fixture",
        input_preprocess_version="fixture-v1",
        modality="audio",
        embedding_dim=1,
        norm=1.0,
        created_at="2026-10-26T00:00:00+00:00",
        latency_ms=0.1,
        window_id="fixture-window",
        interval_ms=(0, 1_000),
        cache_hit=False,
    )
    results: list[EmbeddingResult] = []

    worker.submit(EmbeddingJob(job_id=1, encode=lambda: record), results.append)
    worker.finish(results.append)

    assert controller.status.mode is LoadMode.CRITICAL
    assert [result.record for result in results] == [record]
    assert results[0].inference_ms == record.latency_ms
    assert worker.snapshot()["completed"] == 1
    assert worker.snapshot()["total_inference_ms"] == record.latency_ms
    assert worker.snapshot()["total_worker_elapsed_ms"] > 0
    audio_metrics = worker.snapshot()["by_modality"]["audio"]
    assert audio_metrics["completed"] == 1
    assert audio_metrics["cache_hits"] == 0
    assert audio_metrics["inference_ms"] == record.latency_ms
    assert worker.snapshot()["total_queue_wait_ms"] >= 0


def test_shared_dispatcher_round_robins_sources_with_bounded_pending_work() -> None:
    dispatcher = SharedEmbeddingDispatcher(queue_capacity=3)
    first_started = Event()
    release_first = Event()
    results: list[EmbeddingResult] = []

    def record(job_id: int) -> EmbeddingRecord:
        return EmbeddingRecord(
            embedding=np.ones(1, dtype=np.float32),
            model_revision="fixture",
            input_preprocess_version="fixture-v1",
            modality="image",
            embedding_dim=1,
            norm=1.0,
            created_at="2026-10-26T00:00:00+00:00",
            latency_ms=0.1,
            window_id=f"fixture-{job_id}",
            interval_ms=(job_id, job_id + 1),
            cache_hit=False,
        )

    def encode(job_id: int, *, block: bool = False) -> EmbeddingRecord:
        def run() -> EmbeddingRecord:
            if block:
                first_started.set()
                assert release_first.wait(timeout=2)
            return record(job_id)

        return run()

    assert dispatcher.try_submit(
        "stream-a", EmbeddingJob(0, lambda: encode(0, block=True)), results.append
    )
    assert first_started.wait(timeout=2)
    assert dispatcher.try_submit("stream-a", EmbeddingJob(1, lambda: encode(1)), results.append)
    assert dispatcher.try_submit("stream-a", EmbeddingJob(2, lambda: encode(2)), results.append)
    assert dispatcher.try_submit("stream-b", EmbeddingJob(3, lambda: encode(3)), results.append)
    assert dispatcher.snapshot()["queue_depth"] == 3
    assert not dispatcher.try_submit(
        "stream-c", EmbeddingJob(4, lambda: encode(4)), results.append
    )
    release_first.set()
    dispatcher.close(timeout=3)

    assert [result.job_id for result in results] == [0, 1, 3, 2]
    snapshot = dispatcher.snapshot()
    assert snapshot["queue_depth"] == 0
    assert snapshot["dispatched_count"] == 4
    assert snapshot["by_source"]["stream-a"]["dispatched"] == 3
    assert snapshot["by_source"]["stream-b"]["dispatched"] == 1


def test_shared_dispatcher_runs_distinct_sources_concurrently_in_source_order() -> None:
    dispatcher = SharedEmbeddingDispatcher(queue_capacity=4, worker_count=2)
    first_started = Event()
    second_source_started = Event()
    same_source_second_started = Event()
    release_first = Event()
    release_second = Event()
    guard = Lock()
    active = 0
    peak_active = 0
    results: list[EmbeddingResult] = []

    def encode(job_id: int) -> EmbeddingRecord:
        nonlocal active, peak_active
        with guard:
            active += 1
            peak_active = max(peak_active, active)
        try:
            if job_id == 0:
                first_started.set()
                assert release_first.wait(timeout=3)
            elif job_id == 1:
                same_source_second_started.set()
            elif job_id == 2:
                second_source_started.set()
                assert release_second.wait(timeout=3)
            return EmbeddingRecord(
                embedding=np.ones(1, dtype=np.float32),
                model_revision="fixture",
                input_preprocess_version="fixture-v1",
                modality="audio",
                embedding_dim=1,
                norm=1.0,
                created_at="2026-10-26T00:00:00+00:00",
                latency_ms=0.1,
                window_id=f"concurrent-{job_id}",
                interval_ms=(job_id, job_id + 1),
                cache_hit=False,
            )
        finally:
            with guard:
                active -= 1

    assert dispatcher.try_submit(
        "stream-a", EmbeddingJob(0, lambda: encode(0)), results.append
    )
    assert first_started.wait(timeout=2)
    assert dispatcher.try_submit(
        "stream-a", EmbeddingJob(1, lambda: encode(1)), results.append
    )
    assert dispatcher.try_submit(
        "stream-b", EmbeddingJob(2, lambda: encode(2)), results.append
    )
    assert second_source_started.wait(timeout=2)
    assert not same_source_second_started.is_set()
    assert dispatcher.snapshot()["active_count"] == 2

    release_first.set()
    release_second.set()
    dispatcher.close(timeout=3)

    source_a_order = [result.job_id for result in results if result.job_id in {0, 1}]
    assert source_a_order == [0, 1]
    assert peak_active == 2
    snapshot = dispatcher.snapshot()
    assert snapshot["worker_count"] == 2
    assert snapshot["peak_active"] == 2
    assert snapshot["active_count"] == 0


def test_bounded_worker_delivers_shared_dispatch_results_on_consumer_thread() -> None:
    dispatcher = SharedEmbeddingDispatcher(queue_capacity=2)
    worker = BoundedEmbeddingWorker(
        queue_capacity=1,
        shared_dispatcher=dispatcher,
        source_id="stream-a",
    )
    assert worker._thread is None
    record = EmbeddingRecord(
        embedding=np.ones(1, dtype=np.float32),
        model_revision="fixture",
        input_preprocess_version="fixture-v1",
        modality="audio",
        embedding_dim=1,
        norm=1.0,
        created_at="2026-10-26T00:00:00+00:00",
        latency_ms=0.1,
        window_id="fixture-shared-window",
        interval_ms=(0, 1_000),
        cache_hit=False,
    )
    results: list[EmbeddingResult] = []

    worker.submit(EmbeddingJob(job_id=1, encode=lambda: record), results.append)
    worker.finish(results.append)
    dispatcher.close(timeout=3)

    assert [result.record for result in results] == [record]
    assert worker.snapshot()["by_modality"]["audio"]["completed"] == 1
    assert worker.snapshot()["source_id"] == "stream-a"


def test_shared_dispatcher_bounds_retained_source_stats() -> None:
    dispatcher = SharedEmbeddingDispatcher(queue_capacity=3, source_stats_capacity=2)

    def record(job_id: int) -> EmbeddingRecord:
        return EmbeddingRecord(
            embedding=np.ones(1, dtype=np.float32),
            model_revision="fixture",
            input_preprocess_version="fixture-v1",
            modality="audio",
            embedding_dim=1,
            norm=1.0,
            created_at="2026-10-26T00:00:00+00:00",
            latency_ms=0.1,
            window_id=f"stats-{job_id}",
            interval_ms=(job_id, job_id + 1),
            cache_hit=False,
        )

    results: list[EmbeddingResult] = []
    for job_id, source_id in enumerate(("stream-a", "stream-b", "stream-c")):
        assert dispatcher.try_submit(
            source_id,
            EmbeddingJob(job_id, lambda job_id=job_id: record(job_id)),
            results.append,
        )
    dispatcher.close(timeout=3)

    snapshot = dispatcher.snapshot()
    assert [result.job_id for result in results] == [0, 1, 2]
    assert snapshot["source_stats_capacity"] == 2
    assert set(snapshot["by_source"]) == {"stream-b", "stream-c"}
