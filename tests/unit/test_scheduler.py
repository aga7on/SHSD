from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from shsd.memory import EventStore, TimelineClaim, TimelineEvent
from shsd.workers import (
    AsyncLevelScheduler,
    JobKey,
    LoadMode,
    LoadSample,
    RuntimeLoadController,
    ScheduledJob,
    SubmitResult,
    WorkPriority,
)


def _event(
    event_id: str,
    *,
    level: str = "L1",
    revision: int = 1,
    expected_revision: int = 0,
    state: str = "draft",
    end_ms: int = 1000,
) -> TimelineEvent:
    return TimelineEvent(
        stream_id="stream-1",
        epoch=0,
        event_id=event_id,
        revision=revision,
        start_ms=0,
        end_ms=end_ms,
        kind="music_started",
        level=level,
        state=state,
        modality_mask={"audio": True, "video": False, "speech": False},
        claims=(
            TimelineClaim(
                claim_id=f"claim-{event_id}",
                label="music_present",
                text_ru="Слышна музыка.",
                decision="accepted",
                raw_cosine=0.8,
                margin=0.2,
                evidence_refs=(f"audio:0-{end_ms}",),
                window_ids=(f"window-{event_id}",),
                model_revision="model-r1",
                sample_count=1,
            ),
        ),
        supersedes_revision=expected_revision if expected_revision else None,
    )


def _job(
    event_id: str,
    level: str,
    *,
    revision: int = 1,
    expected_revision: int = 0,
    sources: tuple[TimelineEvent, ...] = (),
) -> ScheduledJob:
    return ScheduledJob(
        key=JobKey("stream-1", 0, event_id, revision, level),  # type: ignore[arg-type]
        expected_revision=expected_revision,
        payload={"test": True},
        source_events=sources,
    )


def test_l1_completes_while_l3_is_still_waiting() -> None:
    async def scenario() -> None:
        l3_started = asyncio.Event()
        release_l3 = asyncio.Event()
        l1_written = asyncio.Event()
        l3_written = asyncio.Event()

        async def l1(job: ScheduledJob) -> TimelineEvent:
            return _event(job.key.event_id, level="L1", revision=job.key.revision)

        async def l2(job: ScheduledJob) -> TimelineEvent:
            return _event(job.key.event_id, level="L2", revision=job.key.revision)

        async def l3(job: ScheduledJob) -> TimelineEvent:
            l3_started.set()
            await release_l3.wait()
            return _event(
                job.key.event_id,
                level="L3",
                revision=job.key.revision,
                state="refined",
            )

        class Writer:
            def append(self, event: TimelineEvent, *, expected_revision: int) -> None:
                if event.level == "L1":
                    l1_written.set()
                if event.level == "L3":
                    l3_written.set()

        scheduler = AsyncLevelScheduler(
            {"L1": l1, "L2": l2, "L3": l3}, Writer(), queue_capacity=2
        )
        scheduler.start()
        source = _event("source-1", state="committed")
        result = scheduler.submit(_job("caption-1", "L3", sources=(source,)))
        assert result == SubmitResult.QUEUED
        await asyncio.wait_for(l3_started.wait(), timeout=0.5)
        assert scheduler.submit(_job("event-1", "L1")) == SubmitResult.QUEUED
        await asyncio.wait_for(l1_written.wait(), timeout=0.5)
        assert not l3_written.is_set()
        release_l3.set()
        await scheduler.close()
        assert l3_written.is_set()
        assert scheduler.completed_count == 2

    asyncio.run(scenario())


def test_queues_are_bounded_and_task_keys_are_deduplicated() -> None:
    async def scenario() -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def process(job: ScheduledJob) -> TimelineEvent:
            if job.key.level == "L1" and job.key.event_id == "first":
                started.set()
                await release.wait()
            return _event(job.key.event_id, level=job.key.level, revision=job.key.revision)

        class Writer:
            def append(self, event: TimelineEvent, *, expected_revision: int) -> None:
                return None

        scheduler = AsyncLevelScheduler(
            {"L1": process, "L2": process, "L3": process},
            Writer(),
            queue_capacity=1,
        )
        scheduler.start()
        first = _job("first", "L1")
        second = _job("second", "L1")
        third = _job("third", "L1")
        assert scheduler.submit(first) == SubmitResult.QUEUED
        await asyncio.wait_for(started.wait(), timeout=0.5)
        assert scheduler.submit(second) == SubmitResult.QUEUED
        assert scheduler.submit(second) == SubmitResult.DUPLICATE
        assert scheduler.submit(first) == SubmitResult.DUPLICATE
        assert scheduler.submit(third) == SubmitResult.FULL
        release.set()
        await scheduler.close()
        assert scheduler.completed_count == 2

    asyncio.run(scenario())


def test_cancel_removes_queued_work_but_does_not_interrupt_an_inflight_worker() -> None:
    async def scenario() -> None:
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        processed: list[str] = []

        async def process(job: ScheduledJob) -> TimelineEvent:
            processed.append(job.key.event_id)
            if job.key.event_id == "first":
                first_started.set()
                await release_first.wait()
            return _event(job.key.event_id, level=job.key.level, revision=job.key.revision)

        class Writer:
            def append(self, event: TimelineEvent, *, expected_revision: int) -> None:
                return None

        scheduler = AsyncLevelScheduler(
            {"L1": process, "L2": process, "L3": process}, Writer(), queue_capacity=2
        )
        scheduler.start()
        first = _job("first", "L1")
        queued = _job("queued", "L1")
        assert scheduler.submit(first) == SubmitResult.QUEUED
        await asyncio.wait_for(first_started.wait(), timeout=0.5)
        assert scheduler.submit(queued) == SubmitResult.QUEUED
        assert not scheduler.cancel(first.key)
        assert scheduler.cancel(queued.key)
        release_first.set()
        await scheduler.close()
        assert processed == ["first"]
        assert scheduler.completed_count == 1
        assert scheduler.cancelled_count == 1

    asyncio.run(scenario())


def test_l3_job_can_batch_only_stable_events_from_one_epoch() -> None:
    stable = (
        _event("source-a", state="committed"),
        _event("source-b", state="refined", end_ms=2000),
    )
    job = _job("caption-group", "L3", sources=stable)
    assert job.source_events == stable

    try:
        _job("caption-group", "L3", sources=(_event("draft-source"),))
    except ValueError as error:
        assert "stable" in str(error)
    else:
        raise AssertionError("draft L1 event must not enter an L3 batch")


def test_compare_and_swap_rejects_late_l1_after_l2_revision() -> None:
    async def scenario() -> None:
        store = EventStore(":memory:")
        store.append(_event("shared-event"), expected_revision=0)
        l1_started = asyncio.Event()
        release_l1 = asyncio.Event()
        l2_written = asyncio.Event()
        failures: list[Exception] = []

        async def l1(job: ScheduledJob) -> TimelineEvent:
            l1_started.set()
            await release_l1.wait()
            return _event(
                job.key.event_id,
                level="L1",
                revision=job.key.revision,
                expected_revision=job.expected_revision,
            )

        async def l2(job: ScheduledJob) -> TimelineEvent:
            return _event(
                job.key.event_id,
                level="L2",
                revision=job.key.revision,
                expected_revision=job.expected_revision,
                state="refined",
            )

        async def l3(job: ScheduledJob) -> TimelineEvent:
            return _event(
                job.key.event_id,
                level="L3",
                revision=job.key.revision,
                expected_revision=job.expected_revision,
                state="refined",
            )

        class Writer:
            def append(self, event: TimelineEvent, *, expected_revision: int) -> None:
                store.append(event, expected_revision=expected_revision)
                if event.level == "L2":
                    l2_written.set()

        scheduler = AsyncLevelScheduler(
            {"L1": l1, "L2": l2, "L3": l3},
            Writer(),
            on_error=lambda job, error: failures.append(error),
        )
        scheduler.start()
        result = scheduler.submit(
            _job("shared-event", "L1", revision=2, expected_revision=1)
        )
        assert result == SubmitResult.QUEUED
        await asyncio.wait_for(l1_started.wait(), timeout=0.5)
        result = scheduler.submit(
            _job("shared-event", "L2", revision=2, expected_revision=1)
        )
        assert result == SubmitResult.QUEUED
        await asyncio.wait_for(l2_written.wait(), timeout=0.5)
        assert store.current("stream-1", 0, "shared-event") is not None
        assert store.current("stream-1", 0, "shared-event").level == "L2"  # type: ignore[union-attr]
        release_l1.set()
        await scheduler.close()
        current = store.current("stream-1", 0, "shared-event")
        assert current is not None and current.revision == 2 and current.level == "L2"
        assert len(failures) == 1
        store.close()

    asyncio.run(scenario())


def test_load_controller_escalates_immediately_and_recovers_with_hysteresis() -> None:
    controller = RuntimeLoadController(recovery_samples=3)
    assert controller.observe(
        LoadSample(queue_depth=75, queue_capacity=100, source_lag_ms=5_000)
    ).mode is LoadMode.DEGRADED
    assert controller.observe(
        LoadSample(queue_depth=96, queue_capacity=100, cpu_percent=96)
    ).mode is LoadMode.CRITICAL
    assert not controller.permits("L2")
    assert controller.permits("L1")
    for _ in range(2):
        assert controller.observe(LoadSample(queue_depth=0, queue_capacity=100)).mode is (
            LoadMode.CRITICAL
        )
    assert controller.observe(LoadSample(queue_depth=0, queue_capacity=100)).mode is (
        LoadMode.NORMAL
    )


def test_shared_load_controller_merges_queue_pressure_and_priority_bands() -> None:
    controller = RuntimeLoadController(recovery_samples=1)
    status = controller.observe(
        LoadSample(
            queue_depth=80,
            queue_capacity=100,
            source_lag_ms=5_500,
            cpu_percent=88,
            rss_bytes=80,
            memory_limit_bytes=100,
        )
    )
    assert status.mode is LoadMode.DEGRADED
    assert controller.permits_priority(WorkPriority.CAPTURE)
    assert controller.permits_priority(WorkPriority.L0_SIGNAL)
    assert controller.permits_priority(WorkPriority.L1)
    assert controller.permits_priority(WorkPriority.L2_ASR)
    assert not controller.permits_priority(WorkPriority.L3_NARRATION)
    assert controller.admit(WorkPriority.EMBEDDING).admitted
    deferred_l3 = controller.admit(WorkPriority.L3_NARRATION)
    assert not deferred_l3.admitted
    assert deferred_l3.reason == "load_degraded"

    status = controller.observe_scheduler(LoadSample(queue_depth=64, queue_capacity=65))
    assert status.mode is LoadMode.CRITICAL
    assert status.sample.queue_depth == 64
    assert status.sample.queue_capacity == 65
    assert status.sample.source_lag_ms == 5_500
    assert status.sample.cpu_percent == 88
    assert controller.permits_priority(WorkPriority.CAPTURE)
    assert controller.permits_priority(WorkPriority.L0_SIGNAL)
    assert controller.permits_priority(WorkPriority.L1)
    assert not controller.permits_priority(WorkPriority.L2_ASR)
    assert not controller.permits_priority(WorkPriority.L3_NARRATION)
    deferred_l2 = controller.admit(WorkPriority.L2_ASR)
    assert not deferred_l2.admitted
    assert deferred_l2.reason == "load_critical"

    status = controller.observe_scheduler(LoadSample(queue_depth=20, queue_capacity=65))
    assert status.sample.queue_depth == 80
    assert status.sample.queue_capacity == 100
    assert status.sample.source_lag_ms == 5_500


def test_shared_load_controller_aggregates_sources_and_forgets_finished_pressure() -> None:
    controller = RuntimeLoadController(recovery_samples=1)
    controller.observe(
        LoadSample(
            queue_depth=10,
            queue_capacity=100,
            source_lag_ms=6_000,
            cpu_percent=88,
            rss_bytes=80,
            memory_limit_bytes=100,
        ),
        source_id="stream-a",
    )
    status = controller.observe(
        LoadSample(queue_depth=96, queue_capacity=100),
        source_id="stream-b",
    )

    assert status.mode is LoadMode.CRITICAL
    assert status.sample.queue_depth == 96
    assert status.sample.source_lag_ms == 6_000
    assert status.sample.cpu_percent == 88
    assert status.sample.rss_bytes == 80

    status = controller.forget("stream-b")
    assert status.mode is LoadMode.DEGRADED
    assert status.sample.queue_depth == 10
    assert status.sample.source_lag_ms == 6_000
    assert controller.external_sample_for("stream-b").queue_depth == 0

    status = controller.forget("stream-a")
    assert status.mode is LoadMode.NORMAL
    assert status.sample.queue_depth == 0
    assert status.sample.source_lag_ms == 0


def test_load_controller_counts_queued_sources_before_capture() -> None:
    controller = RuntimeLoadController()

    for index in range(5):
        controller.register_source(f"queued-{index}")

    assert controller.active_source_count == 5
    assert controller.status.mode is LoadMode.NORMAL
    controller.forget("queued-0")
    assert controller.active_source_count == 4


def test_shared_load_controller_keeps_scheduler_samples_by_source() -> None:
    controller = RuntimeLoadController(recovery_samples=1)
    controller.observe(LoadSample(queue_depth=0, queue_capacity=1), source_id="a")
    controller.observe(LoadSample(queue_depth=0, queue_capacity=1), source_id="b")
    controller.observe_scheduler(
        LoadSample(queue_depth=64, queue_capacity=65), source_id="b"
    )
    status = controller.observe_scheduler(
        LoadSample(queue_depth=0, queue_capacity=1), source_id="a"
    )

    assert status.mode is LoadMode.CRITICAL
    assert status.sample.queue_depth == 64
    assert controller.forget("b").mode is LoadMode.NORMAL


def test_shared_load_controller_accepts_concurrent_live_and_scheduler_samples() -> None:
    controller = RuntimeLoadController()

    def observe_live() -> None:
        for depth in range(500):
            controller.observe(
                LoadSample(
                    queue_depth=depth % 64,
                    queue_capacity=64,
                    source_lag_ms=depth % 7_000,
                    cpu_percent=float(depth % 100),
                )
            )

    def observe_semantic() -> None:
        for depth in range(500):
            controller.observe_scheduler(
                LoadSample(queue_depth=depth % 32, queue_capacity=32)
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(observe_live), pool.submit(observe_semantic)]
        for future in futures:
            future.result()

    sample = controller.status.sample
    assert sample.queue_depth <= sample.queue_capacity
    assert sample.source_lag_ms >= 0
    assert 0 <= sample.cpu_percent <= 100


def test_bounded_queues_signal_saturation_under_2x_and_5x_offered_load() -> None:
    async def scenario(multiplier: int) -> tuple[int, dict[str, object]]:
        started = asyncio.Event()
        release = asyncio.Event()
        reasons: list[str] = []

        async def process(job: ScheduledJob) -> TimelineEvent:
            if job.key.event_id == "running":
                started.set()
                await release.wait()
            return _event(job.key.event_id, level=job.key.level, revision=job.key.revision)

        class Writer:
            def append(self, event: TimelineEvent, *, expected_revision: int) -> None:
                return None

        scheduler = AsyncLevelScheduler(
            {"L1": process, "L2": process, "L3": process},
            Writer(),
            queue_capacity=4,
            on_backpressure=lambda job, reason: reasons.append(reason),
        )
        scheduler.start()
        assert scheduler.submit(_job("running", "L1")) is SubmitResult.QUEUED
        await asyncio.wait_for(started.wait(), timeout=0.5)
        rejected = 0
        for index in range(multiplier * 4):
            result = scheduler.submit(_job(f"offered-{index}", "L1"))
            rejected += result is SubmitResult.FULL
        snapshot = scheduler.snapshot()
        l1_queue = snapshot["queues"]["L1"]  # type: ignore[index]
        assert l1_queue["depth"] <= l1_queue["capacity"]  # type: ignore[index]
        assert snapshot["backpressure_count"] == rejected
        assert len(reasons) == rejected
        assert rejected > 0
        release.set()
        await scheduler.close()
        return rejected, snapshot

    for multiplier in (2, 5):
        rejected, snapshot = asyncio.run(scenario(multiplier))
        assert rejected == multiplier * 4 - 4
        assert snapshot["load"]["mode"] in {"degraded", "critical"}  # type: ignore[index]
