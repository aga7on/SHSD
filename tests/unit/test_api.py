from __future__ import annotations

import asyncio
import json
import time
from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import Any, cast

from fastapi.testclient import TestClient

from shsd.api.app import create_app
from shsd.api.manager import RefineQueueFullError, StreamManager, StreamSession
from shsd.ingest.live import LiveSourceInterruptedError
from shsd.memory import EventStore, TimelineClaim, TimelineEvent, WatermarkTracker
from shsd.workers import LoadSample, RuntimeLoadController, WorkPriority

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "media" / "video_static_3s.mp4"


def _fake_analysis(
    source: Path,
    model: dict[str, Any],
    models_dir: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    stream_id = str(kwargs["stream_id"])
    database_path = Path(kwargs["event_database"])
    emit = kwargs["emit"]
    emit(
        {
            "record_type": "analysis",
            "source_duration_ms": 1_000,
            "modalities": {"available": ["audio"], "unavailable": ["video"]},
        }
    )
    tracker = WatermarkTracker(stream_id, required_modalities={"audio", "video"})
    tracker.mark("C", 0, 1_000, "done", modality="audio")
    tracker.mark("E", 0, 1_000, "done", modality="audio")
    tracker.mark("C", 0, 1_000, "unavailable", modality="video")
    tracker.mark("E", 0, 1_000, "unavailable", modality="video")
    tracker.mark("D", 0, 1_000, "done", level="L1")
    tracker.mark("R", 0, 1_000, "done", level="L1")
    for level in ("L2", "L3"):
        tracker.mark("D", 0, 1_000, "skipped", level=level, reason="not_requested")
        tracker.mark("R", 0, 1_000, "skipped", level=level, reason="not_requested")
    claim = TimelineClaim(
        claim_id="claim-effect",
        label="impact_present",
        text_ru="Обнаружен ударный звук.",
        decision="accepted",
        raw_cosine=0.8,
        margin=0.2,
        evidence_refs=("audio:0-1000",),
        window_ids=("window-0", "window-1"),
        model_revision="embedding-test",
        sample_count=2,
    )
    event = TimelineEvent(
        stream_id=stream_id,
        epoch=0,
        event_id="event-1",
        revision=1,
        start_ms=0,
        end_ms=1_000,
        kind="sound_effect",
        level="L1",
        state="draft",
        modality_mask={"audio": True, "video": False, "speech": False},
        claims=(claim,),
    )
    with EventStore(database_path) as store:
        store.begin_epoch(stream_id, 0)
        store.append(event, expected_revision=0)
        emit({"record_type": "event", **event.to_dict()})
        emit({"record_type": "event", **event.to_dict()})  # Duplicate delivery is ignored.
        refined = replace(
            event,
            revision=2,
            state="refined",
            supersedes_revision=1,
        )
        store.append(refined, expected_revision=1)
        emit({"record_type": "event", **refined.to_dict()})
        emit({"record_type": "event", **event.to_dict()})  # A late stale revision is ignored.
    emit(
        {
            "record_type": "watermark",
            "source_end_ms": 1_000,
            "watermarks": tracker.snapshot(through_ms=1_000).to_dict(),
            "backlog_ms": {"L1": 0, "L2": 1_000, "L3": 1_000},
        }
    )
    metrics = {"record_type": "metrics", "end_to_end_elapsed": 0.01}
    emit(metrics)
    return metrics


def _client(
    tmp_path: Path,
    *,
    journal_limit: int = 32,
    analysis_runner: Any = _fake_analysis,
    load_controller: RuntimeLoadController | None = None,
) -> TestClient:
    manager = StreamManager(
        root=ROOT,
        data_dir=tmp_path,
        analysis_runner=analysis_runner,
        load_controller=load_controller,
        journal_limit=journal_limit,
    )
    return TestClient(create_app(manager=manager))


def test_app_shutdown_closes_shared_embedding_dispatchers(tmp_path: Path) -> None:
    manager = StreamManager(root=ROOT, data_dir=tmp_path)
    dispatcher = manager.embedding_provider_pool.dispatcher_for(cast(Any, object()))
    assert dispatcher._thread.is_alive()

    with TestClient(create_app(manager=manager)):
        pass

    assert not dispatcher._thread.is_alive()


def _fake_export_analysis(
    source: Path,
    model: dict[str, Any],
    models_dir: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    result = _fake_analysis(source, model, models_dir, **kwargs)
    stream_id = str(kwargs["stream_id"])
    database_path = Path(kwargs["event_database"])
    emit = kwargs["emit"]
    with EventStore(database_path) as store:
        event = store.current(stream_id, 0, "event-1")
        assert event is not None
        uncertain_claim = replace(event.claims[0], decision="uncertain")
        revised = replace(
            event,
            revision=event.revision + 1,
            supersedes_revision=event.revision,
            claims=(uncertain_claim,),
        )
        store.append(revised, expected_revision=event.revision)
        if kwargs.get("speech_enabled") is True:
            partial = {
                "record_type": "speech_segment",
                "segment_id": "speech-segment-1",
                "revision": 1,
                "status": "partial",
                "start_ms": 0,
                "end_ms": 1_000,
                "text": "Проверка ASR.",
                "language": "ru",
            }
            final = {
                **partial,
                "revision": 2,
                "supersedes_revision": 1,
                "status": "final",
                "source_complete": True,
            }
            store.append_speech_segment(stream_id, 0, partial)
            store.append_speech_segment(stream_id, 0, final)
        else:
            partial = None
            final = None
    emit({"record_type": "event", **revised.to_dict()})
    if partial is not None and final is not None:
        emit(partial)
        emit(final)
    emit(
        {
            "schema_version": 1,
            "record_type": "caption",
            "caption_ru": "Сохранённое описание ударного звука.",
            "used_claim_ids": ["claim-effect"],
            "new_unsupported_claims": [],
            "time_range": {"start_ms": 0, "end_ms": 1_000},
            "warnings": [],
            "status": "fallback",
            "model_revision": "test-model",
            "prompt_version": "narrator-ru-v1",
            "event_revisions": [{"event_id": "event-1", "revision": revised.revision}],
            "latency_ms": 0,
        }
    )
    return result


def _wait_until_complete(client: TestClient, stream_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        response = client.get(f"/v1/streams/{stream_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("background file analysis did not finish")


def test_local_timeline_ui_redirect_and_assets(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        home = client.get("/", follow_redirects=False)
        assert home.status_code == 307
        assert home.headers["location"] == "/ui/"

        page = client.get("/ui/")
        assert page.status_code == 200
        assert 'id="timeline-chart"' in page.text
        assert 'lang="ru"' in page.text

        styles = client.get("/ui/styles.css")
        script = client.get("/ui/app.js")
        assert styles.status_code == 200
        assert ".cursor-line" in styles.text
        assert script.status_code == 200
        assert 'const API = "/v1/streams"' in script.text


def test_exports_include_revisions_captions_warnings_and_restore_after_restart(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, analysis_runner=_fake_export_analysis) as client:
        created = client.post(
            "/v1/streams",
            json={
                "source": str(FIXTURE),
                "stream_id": "export-replay-test",
                "levels": ["L0", "L1"],
                "speech_enabled": True,
            },
        )
        assert created.status_code == 202
        assert created.json()["speech_enabled"] is True
        stream_id = created.json()["stream_id"]
        assert _wait_until_complete(client, stream_id)["status"] == "completed"

        exported = client.get(f"/v1/streams/{stream_id}/export?format=json")
        assert exported.status_code == 200
        assert "attachment" in exported.headers["content-disposition"]
        payload = exported.json()
        assert payload["speech_segments"][0]["status"] == "final"
        assert payload["speech_segments"][0]["text"] == "Проверка ASR."
        speech = client.get(f"/v1/streams/{stream_id}/speech")
        assert speech.status_code == 200
        assert speech.json()["enabled"] is True
        assert speech.json()["items"][0]["status"] == "final"
        assert [event["revision"] for event in payload["events"]] == [1, 2, 3]
        assert payload["captions"][0]["caption_ru"] == "Сохранённое описание ударного звука."
        warning_kinds = {warning["kind"] for warning in payload["warnings"]}
        assert warning_kinds == {"coverage", "uncertain_claim"}
        assert any(warning["status"] == "unavailable" for warning in payload["warnings"])

        current_only = client.get(
            f"/v1/streams/{stream_id}/export?format=json&include_history=false"
        ).json()
        assert [event["revision"] for event in current_only["events"]] == [3]

        jsonl = client.get(f"/v1/streams/{stream_id}/export?format=jsonl")
        jsonl_rows = [json.loads(line) for line in jsonl.text.splitlines()]
        assert jsonl_rows[0]["record_type"] == "stream_export"
        assert {row["record_type"] for row in jsonl_rows} >= {
            "event", "caption", "speech_segment", "warning", "watermark"
        }

        markdown = client.get(f"/v1/streams/{stream_id}/export?format=markdown")
        assert markdown.headers["content-type"].startswith("text/markdown")
        assert "Сохранённое описание ударного звука." in markdown.text
        assert "uncertain claim" in markdown.text
        assert "Проверка ASR." in markdown.text
        assert "unavailable" in markdown.text

        missing = client.get("/v1/streams/no-such-stream/export")
        assert missing.status_code == 404
        invalid = client.get(f"/v1/streams/{stream_id}/export?format=xml")
        assert invalid.status_code == 422

    restored_manager = StreamManager(
        root=ROOT,
        data_dir=tmp_path,
        analysis_runner=_fake_export_analysis,
    )
    with TestClient(create_app(manager=restored_manager)) as restored:
        status = restored.get(f"/v1/streams/{stream_id}")
        assert status.status_code == 200
        assert status.json()["status"] == "completed"
        assert status.json()["speech_enabled"] is True
        replay = restored.get(
            f"/v1/streams/{stream_id}/timeline?include_history=true"
        ).json()["items"]
        assert [event["revision"] for event in replay] == [1, 2, 3]
        replay_export = restored.get(f"/v1/streams/{stream_id}/export?format=json").json()
        assert replay_export["speech_segments"][0]["status"] == "final"
        assert replay_export["captions"][0]["caption_ru"] == "Сохранённое описание ударного звука."


def test_rest_stream_timeline_watermarks_metrics_and_refine(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        created = client.post(
            "/v1/streams",
            json={
                "source": str(FIXTURE),
                "stream_id": "api-contract-test",
                "levels": ["L0", "L1"],
            },
        )
        assert created.status_code == 202
        assert created.headers["location"] == "/v1/streams/api-contract-test"
        stream_id = created.json()["stream_id"]
        assert _wait_until_complete(client, stream_id)["status"] == "completed"

        current = client.get(f"/v1/streams/{stream_id}/timeline?level=L1").json()
        assert len(current["items"]) == 1
        assert current["items"][0]["revision"] == 2
        history = client.get(
            f"/v1/streams/{stream_id}/timeline?include_history=true"
        ).json()["items"]
        assert [item["revision"] for item in history] == [1, 2]
        detail = client.get(f"/v1/streams/{stream_id}/events/event-1").json()
        assert len(detail["revisions"]) == 2
        assert client.get(f"/v1/streams/{stream_id}/metrics").json()["metrics"][
            "end_to_end_elapsed"
        ] == 0.01
        full_watermarks = client.get(f"/v1/streams/{stream_id}/watermarks").json()[
            "watermarks"
        ]["watermarks"]
        assert full_watermarks["C"] == 1_000
        assert "issues" in full_watermarks
        compact_watermarks = client.get(
            f"/v1/streams/{stream_id}/watermarks?include_issues=false"
        ).json()["watermarks"]["watermarks"]
        assert compact_watermarks["C"] == 1_000
        assert "issues" not in compact_watermarks
        before_refine_seq = client.get(f"/v1/streams/{stream_id}").json()["last_sequence"]

        queued = client.post(
            f"/v1/streams/{stream_id}/refine",
            json={"start_ms": 0, "end_ms": 1_000, "level": "L2"},
        )
        assert queued.status_code == 202
        job_id = queued.json()["job_id"]
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            jobs = client.get(f"/v1/streams/{stream_id}").json()["refine_jobs"]
            if jobs and jobs[0]["status"] in {"completed", "failed"}:
                break
            time.sleep(0.01)
        assert jobs[0]["job_id"] == job_id
        assert jobs[0]["status"] == "completed"
        updated = client.get(
            f"/v1/streams/{stream_id}/timeline?include_history=true"
        ).json()["items"]
        assert [(item["revision"], item["level"]) for item in updated] == [
            (1, "L1"),
            (2, "L1"),
            (3, "L2"),
        ]
        watermarks = client.get(f"/v1/streams/{stream_id}/watermarks").json()[
            "watermarks"
        ]["watermarks"]
        assert watermarks["R"]["L2"] == 1_000
        with client.websocket_connect(
            f"/v1/streams/{stream_id}/ws?after_seq={before_refine_seq}"
        ) as websocket:
            refine_messages = []
            while True:
                message = websocket.receive_json()
                refine_messages.append(message)
                if message["type"] == "stream.refine.completed":
                    break
        assert "stream.event.committed" in [message["type"] for message in refine_messages]


def test_refine_queue_is_bounded_and_coalesces_adjacent_l3_requests(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = StreamManager(
            root=ROOT,
            data_dir=tmp_path,
            analysis_runner=_fake_analysis,
            refine_queue_capacity=2,
        )
        session = StreamSession(
            stream_id="refine-queue-test",
            source=FIXTURE,
            database_path=tmp_path / "refine-queue-test.sqlite3",
            levels=("L1",),
            threads=1,
            window_ms=1_000,
            minimum_similarity=0.6,
            minimum_margin=0.05,
            top_k=3,
            created_at_utc="2026-10-26T00:00:00Z",
            status="completed",
            source_duration_ms=1_000,
        )
        manager._streams[session.stream_id] = session

        first = manager.start_refine(session, start_ms=0, end_ms=500, level="L3")
        second = manager.start_refine(session, start_ms=500, end_ms=1_000, level="L3")
        assert manager.refine_queue_depth == 1
        assert second["coalesced_into"] == first["job_id"]
        assert len(manager._refine_pending) == 1
        assert manager._refine_pending[0].start_ms == 0
        assert manager._refine_pending[0].end_ms == 1_000
        assert len(manager._refine_pending[0].job_ids) == 2

        manager.start_refine(session, start_ms=0, end_ms=1_000, level="L2")
        try:
            manager.start_refine(session, start_ms=0, end_ms=1_000, level="L2")
        except RefineQueueFullError:
            pass
        else:
            raise AssertionError("refine queue accepted work beyond its configured bound")
        assert manager.refine_queue_depth == 2
        task = manager._refine_dispatch_task
        assert task is not None
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_websocket_reconnect_backfills_in_order_and_deduplicates_revisions(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/v1/streams",
            json={"source": str(FIXTURE), "stream_id": "ws-reconnect-test"},
        )
        assert response.status_code == 202
        stream_id = response.json()["stream_id"]
        assert _wait_until_complete(client, stream_id)["status"] == "completed"

        with client.websocket_connect(
            f"/v1/streams/{stream_id}/ws?after_seq=1"
        ) as websocket:
            first = websocket.receive_json()
            second = websocket.receive_json()
        assert first["type"] == "stream.started"
        assert second["type"] == "stream.event.created"
        last_sequence = second["sequence"]

        with client.websocket_connect(
            f"/v1/streams/{stream_id}/ws?after_seq={last_sequence}"
        ) as websocket:
            messages = []
            while True:
                message = websocket.receive_json()
                messages.append(message)
                if message["type"] == "stream.completed":
                    break
        sequences = [message["sequence"] for message in messages]
        assert sequences == sorted(set(sequences))
        assert [message["type"] for message in messages] == [
            "stream.event.revised",
            "stream.watermarks.changed",
            "stream.completed",
        ]
        history = client.get(
            f"/v1/streams/{stream_id}/timeline?include_history=true"
        ).json()["items"]
        assert [event["revision"] for event in history] == [1, 2]


def test_websocket_reports_expired_backfill_window(tmp_path: Path) -> None:
    with _client(tmp_path, journal_limit=3) as client:
        response = client.post(
            "/v1/streams",
            json={"source": str(FIXTURE), "stream_id": "ws-gap-test"},
        )
        assert response.status_code == 202
        stream_id = response.json()["stream_id"]
        assert _wait_until_complete(client, stream_id)["status"] == "completed"

        with client.websocket_connect(f"/v1/streams/{stream_id}/ws?after_seq=0") as websocket:
            gap = websocket.receive_json()
            first_backfill = websocket.receive_json()
            assert gap["type"] == "stream.gap_detected"
            assert gap["data"]["reason"] == "backfill_window_expired"
            assert first_backfill["sequence"] == gap["data"]["to_seq"] + 1


def test_stream_endpoint_accepts_remote_urls(tmp_path: Path) -> None:
    url = "https://example.invalid/live.mp4"
    received_sources: list[str | Path] = []

    def accept_url(source: str | Path, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        received_sources.append(source)
        return {"record_type": "metrics", "end_to_end_elapsed": 0.01}

    with _client(tmp_path, analysis_runner=accept_url) as client:
        response = client.post("/v1/streams", json={"source": url})
        assert response.status_code == 202
        stream_id = response.json()["stream_id"]
        assert _wait_until_complete(client, stream_id)["status"] == "completed"
    assert received_sources == [url]


def test_rtsp_transport_failure_retries_in_a_new_epoch(tmp_path: Path, monkeypatch: Any) -> None:
    import shsd.api.manager as manager_module

    monkeypatch.setattr(manager_module, "_LIVE_RECONNECT_INITIAL_DELAY_SECONDS", 0.001)
    attempts: list[int] = []

    def reconnecting_analysis(
        _source: str | Path,
        _model: dict[str, Any],
        _models_dir: Path,
        **kwargs: Any,
    ) -> dict[str, Any]:
        epoch = int(kwargs["epoch"])
        attempts.append(epoch)
        kwargs["emit"](
            {
                "record_type": "analysis",
                "epoch": epoch,
                "modalities": {"available": ["audio"], "unavailable": ["video"]},
            }
        )
        if len(attempts) == 1:
            raise LiveSourceInterruptedError("publisher disconnected")
        return {"record_type": "metrics", "epoch": epoch, "end_to_end_elapsed": 0.01}

    with _client(tmp_path, analysis_runner=reconnecting_analysis) as client:
        created = client.post(
            "/v1/streams",
            json={
                "source": "rtsp://127.0.0.1:8554/reconnect",
                "stream_id": "rtsp-retry",
            },
        )
        assert created.status_code == 202
        stream_id = created.json()["stream_id"]
        stream = _wait_until_complete(client, stream_id)
        assert stream["status"] == "completed"
        assert stream["epoch"] == 1
        assert attempts == [0, 1]

        with client.websocket_connect(f"/v1/streams/{stream_id}/ws?after_seq=0") as websocket:
            messages = []
            while True:
                message = websocket.receive_json()
                messages.append(message)
                if message["type"] == "stream.completed":
                    break
        assert any(message["type"] == "stream.reconnecting" for message in messages)
        completed = next(message for message in messages if message["type"] == "stream.completed")
        assert completed["data"]["metrics"]["api_reconnect_attempts"] == 1


def test_non_transport_rtsp_failure_is_not_retried(tmp_path: Path) -> None:
    attempts = 0

    def broken_analysis(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("model initialization failed")

    with _client(tmp_path, analysis_runner=broken_analysis) as client:
        created = client.post(
            "/v1/streams",
            json={
                "source": "rtsp://127.0.0.1:8554/no-retry",
                "stream_id": "rtsp-no-retry",
            },
        )
        assert created.status_code == 202
        stream = _wait_until_complete(client, created.json()["stream_id"])
        assert stream["status"] == "failed"
        assert attempts == 1


def test_unexpected_error_during_explicit_stop_is_preserved(tmp_path: Path) -> None:
    started = Event()

    def fail_on_stop(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        started.set()
        assert kwargs["stop_event"].wait(timeout=2)
        raise RuntimeError("decoder cleanup failed")

    with _client(tmp_path, analysis_runner=fail_on_stop) as client:
        created = client.post(
            "/v1/streams",
            json={
                "source": "rtsp://127.0.0.1:8554/stop-error",
                "stream_id": "rtsp-stop-error",
            },
        )
        assert created.status_code == 202
        stream_id = created.json()["stream_id"]
        assert started.wait(timeout=1)
        assert client.delete(f"/v1/streams/{stream_id}").status_code == 202

        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            state = client.get(f"/v1/streams/{stream_id}").json()
            if state["status"] == "stopped":
                break
            time.sleep(0.01)

        assert state["status"] == "stopped"
        assert state["error"] == "RuntimeError: decoder cleanup failed"


def test_delete_interrupts_rtsp_reconnect_backoff(tmp_path: Path, monkeypatch: Any) -> None:
    import shsd.api.manager as manager_module

    monkeypatch.setattr(manager_module, "_LIVE_RECONNECT_INITIAL_DELAY_SECONDS", 10.0)
    attempts = 0

    def disconnected_analysis(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        kwargs["emit"]({"record_type": "analysis", "epoch": kwargs["epoch"]})
        raise LiveSourceInterruptedError("publisher disconnected")

    with _client(tmp_path, analysis_runner=disconnected_analysis) as client:
        created = client.post(
            "/v1/streams",
            json={
                "source": "rtsp://127.0.0.1:8554/delete-during-retry",
                "stream_id": "rtsp-retry-stop",
            },
        )
        assert created.status_code == 202
        stream_id = created.json()["stream_id"]
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = client.get(f"/v1/streams/{stream_id}").json()
            if state["epoch"] == 1:
                break
            time.sleep(0.01)
        assert state["epoch"] == 1
        assert state["status"] == "running"

        stop_started = time.perf_counter()
        stopped = client.delete(f"/v1/streams/{stream_id}")
        assert stopped.status_code == 202
        deadline = stop_started + 1.0
        while time.monotonic() < deadline:
            state = client.get(f"/v1/streams/{stream_id}").json()
            if state["status"] == "stopped":
                break
            time.sleep(0.01)
        assert state["status"] == "stopped"
        assert time.perf_counter() - stop_started < 1.0
        assert attempts == 1


def test_api_streams_share_load_admission_and_remove_finished_samples(tmp_path: Path) -> None:
    controller = RuntimeLoadController(recovery_samples=1)
    pressure_ready = Event()
    observer_checked = Event()
    denied_l2: list[bool] = []
    provider_pools: list[object] = []

    def pressure_analysis(
        _source: str | Path,
        _model: dict[str, Any],
        _models_dir: Path,
        **kwargs: Any,
    ) -> dict[str, Any]:
        stream_id = str(kwargs["stream_id"])
        assert kwargs["runtime_load_controller"] is controller
        assert kwargs["load_source_id"] == stream_id
        provider_pools.append(kwargs["embedding_provider_pool"])
        if stream_id == "load-pressure-owner":
            controller.observe(
                LoadSample(queue_depth=96, queue_capacity=100), source_id=stream_id
            )
            pressure_ready.set()
            assert observer_checked.wait(timeout=5)
        else:
            assert pressure_ready.wait(timeout=5)
            denied_l2.append(not controller.admit(WorkPriority.L2_ASR).admitted)
            observer_checked.set()
        return {"record_type": "metrics", "end_to_end_elapsed": 0.01}

    with _client(
        tmp_path,
        analysis_runner=pressure_analysis,
        load_controller=controller,
    ) as client:
        owner = client.post(
            "/v1/streams",
            json={"source": str(FIXTURE), "stream_id": "load-pressure-owner"},
        )
        observer = client.post(
            "/v1/streams",
            json={"source": str(FIXTURE), "stream_id": "load-pressure-observer"},
        )
        assert owner.status_code == 202
        assert observer.status_code == 202
        assert _wait_until_complete(client, "load-pressure-owner")["status"] == "completed"
        assert _wait_until_complete(client, "load-pressure-observer")["status"] == "completed"

    assert denied_l2 == [True]
    assert len(provider_pools) == 2
    assert provider_pools[0] is provider_pools[1]
    assert controller.status.mode.value == "normal"
    assert controller.status.sample.queue_depth == 0


def test_api_coalesces_backlogged_watermark_callbacks(tmp_path: Path) -> None:
    def emit_many_watermarks(
        _source: str | Path,
        _model: dict[str, Any],
        _models_dir: Path,
        **kwargs: Any,
    ) -> dict[str, Any]:
        emit = kwargs["emit"]
        for capture_ms in range(10_000):
            emit(
                {
                    "record_type": "watermark",
                    "source_end_ms": capture_ms,
                    "watermarks": {"C": capture_ms, "issues": []},
                }
            )
        return {"record_type": "metrics", "end_to_end_elapsed": 0.01}

    with _client(tmp_path, analysis_runner=emit_many_watermarks) as client:
        response = client.post(
            "/v1/streams",
            json={"source": str(FIXTURE), "stream_id": "watermark-coalesce-test"},
        )
        assert response.status_code == 202
        assert _wait_until_complete(client, "watermark-coalesce-test")["status"] == (
            "completed"
        )
        metrics = client.get("/v1/streams/watermark-coalesce-test/metrics").json()[
            "metrics"
        ]
        watermarks = client.get(
            "/v1/streams/watermark-coalesce-test/watermarks?include_issues=false"
        ).json()["watermarks"]["watermarks"]

    assert metrics["api_watermark_records_coalesced"] > 0
    assert watermarks["C"] == 9_999


def test_watermark_metadata_persistence_is_off_loop_and_coalesced(
    tmp_path: Path, monkeypatch: Any
) -> None:
    manager = StreamManager(root=ROOT, data_dir=tmp_path)
    session = StreamSession(
        stream_id="metadata-offload-test",
        source=FIXTURE,
        database_path=tmp_path / "metadata-offload-test.sqlite3",
        levels=("L0", "L1"),
        threads=1,
        window_ms=1_000,
        minimum_similarity=0.6,
        minimum_margin=0.05,
        top_k=3,
        created_at_utc="2026-10-26T00:00:00+00:00",
    )
    original_persist = manager._persist_session
    persistence_started = Event()
    release_persistence = Event()
    write_count = 0

    def slow_persist(target: StreamSession) -> None:
        nonlocal write_count
        write_count += 1
        if write_count == 1:
            persistence_started.set()
            assert release_persistence.wait(5)
        original_persist(target)

    monkeypatch.setattr(manager, "_persist_session", slow_persist)
    started = time.perf_counter()
    manager._handle_analysis_record(
        session,
        {"record_type": "watermark", "watermarks": {"C": 0, "issues": []}},
    )
    callback_elapsed = time.perf_counter() - started

    assert callback_elapsed < 0.2
    assert persistence_started.wait(1)
    for capture_ms in range(1, 101):
        session.watermarks = {"watermarks": {"C": capture_ms}}
        manager._schedule_session_persist(session)
    assert manager._metadata_persistence_coalesced[session.stream_id] >= 90

    release_persistence.set()
    assert manager._wait_for_session_persistence(session, timeout=5)
    with EventStore(session.database_path) as store:
        metadata = store.load_stream_metadata(session.stream_id)

    assert metadata is not None
    assert metadata["watermarks"] == {"watermarks": {"C": 100}}
    assert write_count <= 2


def test_stream_endpoint_rejects_unsupported_sources_and_invalid_intervals(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        unsupported = client.post(
            "/v1/streams", json={"source": "ftp://example.invalid/live.mp4"}
        )
        assert unsupported.status_code == 422
        invalid = client.post(
            "/v1/streams",
            json={"source": str(FIXTURE), "stream_id": "interval-test"},
        )
        assert invalid.status_code == 202
        stream_id = invalid.json()["stream_id"]
        assert _wait_until_complete(client, stream_id)["status"] == "completed"
        bad_range = client.post(
            f"/v1/streams/{stream_id}/refine",
            json={"start_ms": 500, "end_ms": 400, "level": "L2"},
        )
        assert bad_range.status_code == 422


def test_analysis_failure_is_exposed_in_stream_status_and_websocket(tmp_path: Path) -> None:
    def fail_analysis(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        raise RuntimeError("synthetic worker failure")

    with _client(tmp_path, analysis_runner=fail_analysis) as client:
        response = client.post(
            "/v1/streams",
            json={"source": str(FIXTURE), "stream_id": "worker-error-test"},
        )
        assert response.status_code == 202
        stream_id = response.json()["stream_id"]
        state = _wait_until_complete(client, stream_id)
        assert state["status"] == "failed"
        assert state["health"] == "error"
        assert "synthetic worker failure" in state["error"]

        with client.websocket_connect(
            f"/v1/streams/{stream_id}/ws?after_seq=1"
        ) as websocket:
            assert websocket.receive_json()["type"] == "stream.started"
            error_message = websocket.receive_json()
        assert error_message["type"] == "stream.error"
        assert error_message["data"]["code"] == "analysis_failed"
