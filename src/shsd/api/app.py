"""FastAPI v0 REST and replayable WebSocket surface for local SHSD runs."""

from __future__ import annotations

import importlib
import time
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from shsd.api.exports import build_export_payload, render_jsonl, render_markdown
from shsd.api.manager import RefineLevel, RefineQueueFullError, StreamLevel, StreamManager


def _default_levels() -> list[StreamLevel]:
    return ["L0", "L1"]


class CreateStreamRequest(BaseModel):
    """Options for a bounded local file or URL analysis job."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=4_096)
    stream_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    levels: list[StreamLevel] = Field(default_factory=_default_levels, min_length=1)
    threads: int = Field(default=4, ge=1, le=64)
    window_ms: int = Field(default=5_000, ge=250, le=60_000)
    minimum_similarity: float = Field(default=0.60, ge=-1.0, le=1.0)
    minimum_margin: float = Field(default=0.05, ge=0.0, le=2.0)
    top_k: int = Field(default=3, ge=1, le=20)
    speech_enabled: bool = False
    sampling_profile: Literal["standard", "adaptive"] = "standard"
    vision_profile: Literal["standard", "compact"] = "standard"
    prefetch_overflow_policy: Literal["block", "drop_newest", "drop_oldest"] | None = None
    prefetch_capacity: int | None = Field(default=None, ge=1, le=256)


class RefineRequest(BaseModel):
    """Request a committed L2 refinement or L3 narration for a source interval."""

    model_config = ConfigDict(extra="forbid")

    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    level: RefineLevel


def create_app(
    *,
    manager: StreamManager | None = None,
    root: Path | None = None,
    data_dir: Path | None = None,
    models_dir: Path | None = None,
    cache_dir: Path | None = None,
    embedding_concurrency: int = 1,
) -> FastAPI:
    """Create the v0 API app; defaults to local repository paths and state."""
    repo_root = (root or Path(__file__).resolve().parents[3]).resolve()
    stream_manager = manager or StreamManager(
        root=repo_root,
        data_dir=data_dir or Path.cwd() / "runs" / "shsd",
        models_dir=models_dir,
        cache_dir=cache_dir,
        embedding_concurrency=embedding_concurrency,
    )
    app = FastAPI(
        title="SHSD local timeline API",
        version="0.1.0",
        description="CPU-first local media analysis with revisioned events and watermarks.",
    )
    app.state.stream_manager = stream_manager
    app.router.add_event_handler("shutdown", stream_manager.shutdown)

    @app.get("/v1/streams")
    def list_streams() -> dict[str, object]:
        items = [
            stream_manager.stream_payload(session)
            for session in stream_manager.sessions()
        ]
        return {"schema_version": 1, "items": items}

    @app.post("/v1/streams", status_code=202)
    async def create_stream(body: CreateStreamRequest) -> JSONResponse:
        if "://" in body.source:
            try:
                parsed = urlsplit(body.source)
                hostname = parsed.hostname
            except ValueError as error:
                raise HTTPException(status_code=422, detail="invalid media URL") from error
            if parsed.scheme.lower() not in {"http", "https", "rtsp", "rtsps"} or not hostname:
                raise HTTPException(
                    status_code=422,
                    detail="source URL must use http, https, rtsp, or rtsps and include a host",
                )
            source: str | Path = body.source
            is_live_source = parsed.scheme.lower() in {"rtsp", "rtsps"}
        else:
            source = Path(body.source).expanduser().resolve()
            is_live_source = False
            if not source.is_file():
                raise HTTPException(
                    status_code=404, detail=f"local media file not found: {source}"
                )
        overflow_policy = body.prefetch_overflow_policy or (
            "drop_oldest" if is_live_source else "block"
        )
        if is_live_source and overflow_policy == "block":
            raise HTTPException(
                status_code=422,
                detail="live RTSP sources require drop_newest or drop_oldest overflow policy",
            )
        try:
            session = stream_manager.create_stream(
                source=source,
                stream_id=body.stream_id,
                levels=tuple(dict.fromkeys(body.levels)),
                threads=body.threads,
                window_ms=body.window_ms,
                minimum_similarity=body.minimum_similarity,
                minimum_margin=body.minimum_margin,
                top_k=body.top_k,
                speech_enabled=body.speech_enabled,
                sampling_profile=body.sampling_profile,
                vision_profile=body.vision_profile,
                prefetch_overflow_policy=overflow_policy,
                prefetch_capacity=body.prefetch_capacity,
            )
        except KeyError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return JSONResponse(
            status_code=202,
            headers={"Location": f"/v1/streams/{session.stream_id}"},
            content=stream_manager.stream_payload(session),
        )

    @app.delete("/v1/streams/{stream_id}", status_code=202)
    async def stop_stream(stream_id: str) -> dict[str, Any]:
        session = stream_manager.get(stream_id)
        if session is None:
            raise HTTPException(status_code=404, detail="stream not found")
        try:
            stream_manager.stop_stream(session)
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return stream_manager.stream_payload(session)

    @app.get("/v1/streams/{stream_id}")
    def get_stream(stream_id: str) -> dict[str, object]:
        session = stream_manager.get(stream_id)
        if session is None:
            raise HTTPException(status_code=404, detail="stream not found")
        return stream_manager.stream_payload(session)

    @app.get("/v1/streams/{stream_id}/timeline")
    def get_timeline(
        stream_id: str,
        from_ms: Annotated[int | None, Query(ge=0)] = None,
        to_ms: Annotated[int | None, Query(gt=0)] = None,
        level: str | None = None,
        include_history: bool = False,
        limit: Annotated[int, Query(ge=1, le=1_000)] = 500,
    ) -> dict[str, object]:
        session = stream_manager.get(stream_id)
        if session is None:
            raise HTTPException(status_code=404, detail="stream not found")
        if from_ms is not None and to_ms is not None and to_ms <= from_ms:
            raise HTTPException(status_code=422, detail="to_ms must be greater than from_ms")
        if level is not None and level not in {"L0", "L1", "L2", "L3"}:
            raise HTTPException(status_code=422, detail="level must be L0, L1, L2, or L3")
        items = stream_manager.timeline(
            session,
            from_ms=from_ms,
            to_ms=to_ms,
            level=level,
            include_history=include_history,
            limit=limit,
        )
        return {
            "schema_version": 1,
            "stream_id": stream_id,
            "epoch": session.epoch,
            "items": items,
            "include_history": include_history,
        }

    @app.get("/v1/streams/{stream_id}/watermarks")
    def get_watermarks(
        stream_id: str,
        include_issues: bool = True,
    ) -> dict[str, object]:
        session = stream_manager.get(stream_id)
        if session is None:
            raise HTTPException(status_code=404, detail="stream not found")
        watermarks = session.watermarks
        if not include_issues and isinstance(watermarks, dict):
            compact_record = dict(watermarks)
            snapshot = compact_record.get("watermarks")
            if isinstance(snapshot, dict):
                compact_record["watermarks"] = {
                    key: value for key, value in snapshot.items() if key != "issues"
                }
            watermarks = compact_record
        return {
            "schema_version": 1,
            "stream_id": stream_id,
            "epoch": session.epoch,
            "status": session.status,
            "watermarks": watermarks,
        }

    @app.get("/v1/streams/{stream_id}/speech")
    def get_speech_segments(
        stream_id: str,
        from_ms: Annotated[int | None, Query(ge=0)] = None,
        to_ms: Annotated[int | None, Query(gt=0)] = None,
        limit: Annotated[int, Query(ge=1, le=10_000)] = 1_000,
    ) -> dict[str, object]:
        session = stream_manager.get(stream_id)
        if session is None:
            raise HTTPException(status_code=404, detail="stream not found")
        if from_ms is not None and to_ms is not None and to_ms <= from_ms:
            raise HTTPException(status_code=422, detail="to_ms must be greater than from_ms")
        end_ms = to_ms or session.source_duration_ms or 0
        start_ms = from_ms if from_ms is not None else max(0, end_ms - 600_000)
        return {
            "schema_version": 1,
            "stream_id": stream_id,
            "epoch": session.epoch,
            "enabled": session.speech_enabled,
            "items": stream_manager.speech_segments(
                session, from_ms=start_ms, to_ms=to_ms, limit=limit
            ),
        }

    @app.get("/v1/streams/{stream_id}/metrics")
    def get_metrics(stream_id: str) -> dict[str, object]:
        session = stream_manager.get(stream_id)
        if session is None:
            raise HTTPException(status_code=404, detail="stream not found")
        metrics = dict(session.metrics) if session.metrics is not None else None
        elapsed = metrics.get("end_to_end_elapsed") if metrics else None
        revisions = metrics.get("event_revision_count", 0) if metrics else 0
        throughput = (
            round(float(revisions) / float(elapsed), 3)
            if isinstance(elapsed, (int, float)) and elapsed > 0
            else None
        )
        try:
            psutil_module: Any = importlib.import_module("psutil")
            process = psutil_module.Process()
            resources: dict[str, object] = {
                "rss_bytes": process.memory_info().rss,
                "cpu_percent": process.cpu_percent(interval=None),
            }
        except ImportError:
            resources = {"available": False}
        return {
            "schema_version": 1,
            "stream_id": stream_id,
            "epoch": session.epoch,
            "status": session.status,
            "metrics": metrics,
            "throughput_event_revisions_per_second": throughput,
            "resources": resources,
            "observed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "queue_lengths": {
                "file_analysis": int(session.status in {"queued", "running"}),
                "refine": stream_manager.refine_queue_depth,
                "L1": None,
                "L2": None,
                "L3": None,
            },
        }

    @app.get("/v1/streams/{stream_id}/events/{event_id}")
    def get_event(stream_id: str, event_id: str) -> dict[str, object]:
        session = stream_manager.get(stream_id)
        if session is None:
            raise HTTPException(status_code=404, detail="stream not found")
        revisions = stream_manager.event_detail(session, event_id)
        if not revisions:
            raise HTTPException(status_code=404, detail="event not found")
        return {
            "schema_version": 1,
            "stream_id": stream_id,
            "epoch": session.epoch,
            "event_id": event_id,
            "revisions": revisions,
        }

    @app.get("/v1/streams/{stream_id}/export")
    def export_stream(
        stream_id: str,
        export_format: Annotated[
            Literal["json", "jsonl", "markdown"], Query(alias="format")
        ] = "json",
        include_history: bool = True,
    ) -> Response:
        session = stream_manager.get(stream_id)
        if session is None:
            raise HTTPException(status_code=404, detail="stream not found")
        events = stream_manager.timeline(
            session,
            from_ms=None,
            to_ms=None,
            level=None,
            include_history=include_history,
            limit=1_000,
        )
        payload = build_export_payload(
            stream_id=stream_id,
            epoch=session.epoch,
            source=str(session.source),
            status=session.status,
            events=events,
            captions=stream_manager.captions(session),
            speech_segments=stream_manager.speech_segments(session, limit=10_000),
            watermarks=session.watermarks,
            include_history=include_history,
        )
        filename = f"shsd-{stream_id}.{export_format}"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        if export_format == "json":
            return JSONResponse(payload, headers=headers)
        if export_format == "jsonl":
            return PlainTextResponse(
                render_jsonl(payload), media_type="application/x-ndjson", headers=headers
            )
        return PlainTextResponse(
            render_markdown(payload), media_type="text/markdown", headers=headers
        )

    @app.post("/v1/streams/{stream_id}/refine", status_code=202)
    async def refine(stream_id: str, body: RefineRequest) -> JSONResponse:
        session = stream_manager.get(stream_id)
        if session is None:
            raise HTTPException(status_code=404, detail="stream not found")
        if body.end_ms <= body.start_ms:
            raise HTTPException(status_code=422, detail="end_ms must be greater than start_ms")
        try:
            job = stream_manager.start_refine(
                session,
                start_ms=body.start_ms,
                end_ms=body.end_ms,
                level=body.level,
            )
        except RefineQueueFullError as error:
            raise HTTPException(status_code=429, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return JSONResponse(
            status_code=202,
            headers={"Location": f"/v1/streams/{stream_id}/refine/{job['job_id']}"},
            content={"schema_version": 1, "stream_id": stream_id, **job},
        )

    @app.websocket("/v1/streams/{stream_id}/ws")
    async def stream_events(
        websocket: WebSocket,
        stream_id: str,
        after_seq: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        session = stream_manager.get(stream_id)
        if session is None:
            await websocket.close(code=1008, reason="stream not found")
            return
        if after_seq > session.sequence:
            await websocket.close(code=1008, reason="after_seq is ahead of the stream")
            return
        await websocket.accept()
        queue, backlog = stream_manager.subscribe(session, after_seq)
        try:
            for message in backlog:
                await websocket.send_json(message)
            while True:
                await websocket.send_json(await queue.get())
        except WebSocketDisconnect:
            pass
        finally:
            stream_manager.unsubscribe(session, queue)

    app.mount(
        "/ui",
        StaticFiles(directory=Path(__file__).with_name("static"), html=True),
        name="ui",
    )

    @app.get("/", include_in_schema=False)
    def ui_home() -> RedirectResponse:
        return RedirectResponse(url="/ui/", status_code=307)

    return app


app = create_app()
