from __future__ import annotations

import threading

import numpy as np

from shsd.workers.asr_worker import (
    BoundedSpeechWorker,
    SpeechResult,
    SpeechTask,
    SpeechWindowAssembler,
)
from shsd.workers.scheduler import LoadSample, RuntimeLoadController


def test_speech_window_assembler_splits_and_keeps_pts_ranges() -> None:
    assembler = SpeechWindowAssembler(window_ms=1_000)
    first = np.zeros(8_000, dtype=np.float32)
    second = np.ones(8_000, dtype=np.float32)

    assert assembler.push(0, first) == []
    tasks = assembler.push(500, second)
    trailing = assembler.flush()

    assert [(task.start_ms, task.end_ms, task.samples.size) for task in tasks] == [
        (0, 1_000, 16_000),
    ]
    assert trailing is None
    assert float(tasks[0].samples.mean()) == 0.5


def test_speech_window_assembler_flushes_before_a_timestamp_gap() -> None:
    assembler = SpeechWindowAssembler(window_ms=1_000)
    first = np.zeros(8_000, dtype=np.float32)
    second = np.ones(8_000, dtype=np.float32)

    assert assembler.push(0, first) == []
    emitted = assembler.push(2_000, second)
    trailing = assembler.flush()

    assert [(task.start_ms, task.end_ms) for task in emitted] == [(0, 500)]
    assert trailing is not None
    assert (trailing.start_ms, trailing.end_ms) == (2_000, 2_500)


def test_bounded_speech_worker_reports_queue_pressure_without_blocking() -> None:
    entered = threading.Event()
    release = threading.Event()
    results: list[SpeechResult] = []

    def transcribe(samples: np.ndarray) -> str:
        entered.set()
        release.wait(timeout=2)
        return str(int(samples[0]))

    worker = BoundedSpeechWorker(transcribe, queue_capacity=1, result_capacity=1)
    assert worker.submit(SpeechTask(0, 100, np.array([1], dtype=np.float32)))
    assert entered.wait(timeout=2)
    assert worker.submit(SpeechTask(100, 200, np.array([2], dtype=np.float32)))
    assert not worker.submit(SpeechTask(200, 300, np.array([3], dtype=np.float32)))

    release.set()
    worker.finish(results.append)

    assert [(item.start_ms, item.text, item.status) for item in results] == [
        (0, "1", "complete"),
        (100, "2", "complete"),
    ]


def test_bounded_speech_worker_isolates_transcriber_errors() -> None:
    results: list[SpeechResult] = []

    def transcribe(samples: np.ndarray) -> str:
        if samples[0] < 0:
            raise RuntimeError("fixture failure")
        return "ok"

    worker = BoundedSpeechWorker(transcribe)
    assert worker.submit(SpeechTask(0, 100, np.array([-1], dtype=np.float32)))
    assert worker.submit(SpeechTask(100, 200, np.array([1], dtype=np.float32)))
    worker.finish(results.append)

    assert results[0].status == "failed"
    assert "fixture failure" in (results[0].error or "")
    assert results[1].status == "complete"
    assert results[1].text == "ok"


def test_asr_lane_uses_shared_admission_and_drops_p3_during_critical_load() -> None:
    controller = RuntimeLoadController()
    controller.observe(LoadSample(queue_depth=96, queue_capacity=100))
    worker = BoundedSpeechWorker(lambda _samples: "unused", load_controller=controller)
    task = SpeechTask(0, 100, np.array([1], dtype=np.float32))

    assert not worker.submit(task)
    assert worker.last_submit_reason == "load_critical"
    assert worker.outstanding == 0
    assert worker.snapshot()["admission_capacity"] == 11
    worker.finish(lambda _result: None)
