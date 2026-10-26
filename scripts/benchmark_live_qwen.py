"""Measure L1/L2/L3 progress on a real RTSP stream, with an optional no-L3 control.

The report separates work published while the RTSP publisher is still sending
media from work completed after the publisher exits. This matters because file
analysis may drain its queues and narrate only at end of stream.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import socket
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "benchmarks" / "fixtures" / "real_poc" / "tears_of_steel_120_210s.mp4"
DEFAULT_OUTPUT = ROOT / "benchmarks" / "reports" / "live_qwen_real_tears_20261026"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={"Content-Type": "application/json"} if payload is not None else {},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))


def _wait_for_port(port: int, process: subprocess.Popen[Any], timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"service exited early with code {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"port {port} did not open in {timeout}s")


def _stop_process(process: subprocess.Popen[Any] | None, timeout: float = 10) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def _watermark_snapshot(base_url: str, stream_id: str) -> dict[str, Any]:
    return _request_json(f"{base_url}/v1/streams/{stream_id}/watermarks?include_issues=false")


def _export(base_url: str, stream_id: str) -> dict[str, Any]:
    return _request_json(
        f"{base_url}/v1/streams/{stream_id}/export?format=json&include_history=true"
    )


def _record_snapshot(
    base_url: str,
    stream_id: str,
    *,
    publisher_elapsed_s: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    watermark = _watermark_snapshot(base_url, stream_id)
    payload = _export(base_url, stream_id)
    watermark_record = watermark.get("watermarks")
    progress = watermark_record.get("watermarks", {}) if isinstance(watermark_record, dict) else {}
    if not isinstance(progress, dict):
        progress = {}
    sample = {
        "publisher_elapsed_s": round(publisher_elapsed_s, 3),
        "status": watermark.get("status"),
        "capture_C_ms": progress.get("C", 0),
        "embedding_E_ms": progress.get("E", 0),
        "L1_D_ms": progress.get("D", {}).get("L1", 0),
        "L2_D_ms": progress.get("D", {}).get("L2", 0),
        "L3_D_ms": progress.get("D", {}).get("L3", 0),
        "L1_R_ms": progress.get("R", {}).get("L1", 0),
        "L2_R_ms": progress.get("R", {}).get("L2", 0),
        "L3_R_ms": progress.get("R", {}).get("L3", 0),
        "event_count": len(payload.get("events", [])),
        "caption_count": len(payload.get("captions", [])),
    }
    return sample, payload


def _caption_key(caption: dict[str, Any]) -> str:
    return json.dumps(
        {
            "caption_ru": caption.get("caption_ru"),
            "event_revisions": caption.get("event_revisions", []),
            "status": caption.get("status"),
            "time_range": caption.get("time_range", {}),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _observe_captions(
    payload: dict[str, Any],
    *,
    elapsed_s: float,
    first_seen: dict[str, float],
) -> None:
    for caption in payload.get("captions", []):
        if isinstance(caption, dict):
            first_seen.setdefault(_caption_key(caption), elapsed_s)


def _latency_summary(values: list[int]) -> dict[str, int | float]:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    p95 = ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]
    return {
        "count": len(ordered),
        "median_ms": statistics.median(ordered),
        "p95_ms": p95,
        "max_ms": max(ordered),
    }


def _runtime_metrics_summary(metrics: dict[str, Any] | None) -> dict[str, Any] | None:
    if metrics is None:
        return None
    ingest = metrics.get("media_ingest", {})
    prefetch = metrics.get("prefetch", {})
    embedding = metrics.get("embedding_worker", {})
    resources = metrics.get("process_resources", {})
    return {
        "end_to_end_elapsed_s": metrics.get("end_to_end_elapsed"),
        "event_revision_count": metrics.get("event_revision_count"),
        "peak_process_tree_rss_bytes": resources.get("peak_process_tree_rss_bytes"),
        "media_ingest_packet_count": ingest.get("packets"),
        "media_ingest_drop_count": ingest.get("dropped_count"),
        "shared_prefetch_drop_count": prefetch.get("shared", {}).get("dropped_count"),
        "embedding_by_modality": {
            modality: {
                key: stats.get(key)
                for key in ("completed", "cache_hits", "inference_ms", "queue_wait_ms")
            }
            for modality, stats in embedding.get("by_modality", {}).items()
        },
        "narration_backend_counts": metrics.get("narration_backend_counts"),
        "narration_fallback_count": metrics.get("narration_fallback_count"),
        "narration_latency_ms_samples": metrics.get("narration_latency_ms_samples", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mediamtx", type=Path, required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--shsd", type=Path, default=ROOT / ".venv" / "Scripts" / "shsd.exe")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--window-ms", type=int, default=5_000)
    parser.add_argument(
        "--disable-l3",
        action="store_true",
        help="disable L3/Qwen to measure upstream capture and L1/L2 without narration",
    )
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--live-seconds", type=float, default=90.0)
    parser.add_argument("--loop-input", action="store_true")
    parser.add_argument("--post-stream-timeout-seconds", type=float, default=240)
    args = parser.parse_args()
    levels = ["L0", "L1", "L2"] if args.disable_l3 else ["L0", "L1", "L2", "L3"]

    source = args.source.resolve()
    mediamtx_path = args.mediamtx.resolve()
    ffmpeg = shutil.which(args.ffmpeg) or args.ffmpeg
    if not source.is_file() or not mediamtx_path.is_file():
        parser.error("source video and mediamtx executable must exist")
    if args.threads < 1 or args.poll_seconds <= 0 or args.live_seconds <= 0:
        parser.error("threads and timing values must be positive")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("run_%Y%m%dT%H%M%S%f")
    state_dir = output_dir / "state" / run_id
    cache_dir = args.cache_dir.resolve() if args.cache_dir else output_dir / "cache" / run_id
    state_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    rtsp_port, api_port = _free_port(), _free_port()
    api_url = f"http://127.0.0.1:{api_port}"
    config_path = output_dir / "mediamtx.yml"
    config_path.write_text(
        "logLevel: info\n"
        "logDestinations: [stdout]\n"
        "rtsp: true\n"
        f"rtspAddress: 127.0.0.1:{rtsp_port}\n"
        "api: false\n"
        "paths:\n"
        "  all_others:\n",
        encoding="utf-8",
    )
    media_log = (output_dir / "mediamtx.log").open("wb")
    api_log = (output_dir / "api.log").open("wb")
    publisher_log = (output_dir / "publisher.log").open("wb")
    mediamtx: subprocess.Popen[Any] | None = None
    api: subprocess.Popen[Any] | None = None
    publisher: subprocess.Popen[Any] | None = None
    samples: list[dict[str, Any]] = []
    payload: dict[str, Any] = {}
    stream_id = "live-qwen-tears"
    publisher_started_utc: datetime | None = None
    publisher_started = 0.0
    publisher_ended = 0.0
    pre_stop_refine_result: dict[str, Any] | None = None
    pre_stop_caption_count: int | None = None
    pre_stop_watermark: dict[str, Any] | None = None
    terminal_payload: dict[str, Any] = {}
    terminal_watermark: dict[str, Any] = {}
    terminal_status: dict[str, Any] = {}
    caption_first_seen: dict[str, float] = {}
    try:
        mediamtx = subprocess.Popen(
            [str(mediamtx_path), str(config_path)],
            cwd=output_dir,
            stdout=media_log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _wait_for_port(rtsp_port, mediamtx)
        api = subprocess.Popen(
            [
                str(args.shsd.resolve()),
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
                "--data-dir",
                str(state_dir),
                "--models-dir",
                str(ROOT / "models"),
                "--cache-dir",
                str(cache_dir),
            ],
            cwd=ROOT,
            stdout=api_log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        api_deadline = time.monotonic() + 60
        while time.monotonic() < api_deadline:
            if api.poll() is not None:
                raise RuntimeError(f"SHSD API exited early with code {api.returncode}")
            try:
                _request_json(f"{api_url}/v1/streams", timeout=1)
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise TimeoutError("SHSD API did not become ready")

        publisher_command = [
            ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "warning",
        ]
        if args.loop_input:
            publisher_command.extend(["-stream_loop", "-1"])
        publisher_command.extend(
            [
                "-re",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-c",
                "copy",
                "-f",
                "rtsp",
                "-rtsp_transport",
                "tcp",
                f"rtsp://127.0.0.1:{rtsp_port}/tears",
            ]
        )
        publisher = subprocess.Popen(
            publisher_command,
            cwd=ROOT,
            stdout=publisher_log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        publisher_started = time.monotonic()
        publisher_started_utc = datetime.now(UTC)
        time.sleep(0.4)
        _request_json(
            f"{api_url}/v1/streams",
            method="POST",
            body={
                "source": f"rtsp://127.0.0.1:{rtsp_port}/tears",
                "stream_id": stream_id,
                "levels": levels,
                "threads": args.threads,
                "window_ms": args.window_ms,
                "sampling_profile": "standard",
                "vision_profile": "standard",
                "prefetch_overflow_policy": "drop_oldest",
                "prefetch_capacity": 8,
            },
        )

        first_capture_deadline = time.monotonic() + 60
        while time.monotonic() < first_capture_deadline:
            sample, payload = _record_snapshot(
                api_url, stream_id, publisher_elapsed_s=time.monotonic() - publisher_started
            )
            samples.append(sample)
            _observe_captions(
                payload,
                elapsed_s=sample["publisher_elapsed_s"],
                first_seen=caption_first_seen,
            )
            if sample["capture_C_ms"] > 0:
                break
            if publisher.poll() is not None:
                raise RuntimeError("RTSP publisher ended before SHSD captured a frame")
            time.sleep(args.poll_seconds)

        while time.monotonic() - publisher_started < args.live_seconds:
            sample, payload = _record_snapshot(
                api_url, stream_id, publisher_elapsed_s=time.monotonic() - publisher_started
            )
            samples.append(sample)
            _observe_captions(
                payload,
                elapsed_s=sample["publisher_elapsed_s"],
                first_seen=caption_first_seen,
            )
            if (
                not args.disable_l3
                and pre_stop_refine_result is None
                and sample["capture_C_ms"] >= 10_000
            ):
                pre_stop_watermark = _watermark_snapshot(api_url, stream_id)
                pre_stop_caption_count = len(payload.get("captions", []))
                try:
                    _request_json(
                        f"{api_url}/v1/streams/{stream_id}/refine",
                        method="POST",
                        body={"start_ms": 0, "end_ms": sample["capture_C_ms"], "level": "L3"},
                    )
                    pre_stop_refine_result = {"http_status": 202}
                except urllib.error.HTTPError as error:
                    pre_stop_refine_result = {
                        "http_status": error.code,
                        "body": error.read().decode("utf-8", errors="replace"),
                    }
            remaining = args.live_seconds - (time.monotonic() - publisher_started)
            if remaining > 0:
                time.sleep(min(args.poll_seconds, remaining))

        publisher_ended = time.monotonic()
        publisher_elapsed_s = publisher_ended - publisher_started
        stop_requested_elapsed_s = publisher_elapsed_s
        pre_stop_watermark = _watermark_snapshot(api_url, stream_id)
        pre_stop_caption_count = len(payload.get("captions", []))
        stop_response = _request_json(f"{api_url}/v1/streams/{stream_id}", method="DELETE")
        post_deadline = time.monotonic() + args.post_stream_timeout_seconds
        while time.monotonic() < post_deadline:
            sample, payload = _record_snapshot(
                api_url, stream_id, publisher_elapsed_s=time.monotonic() - publisher_started
            )
            samples.append(sample)
            _observe_captions(
                payload,
                elapsed_s=sample["publisher_elapsed_s"],
                first_seen=caption_first_seen,
            )
            terminal_status = _request_json(f"{api_url}/v1/streams/{stream_id}")
            if terminal_status.get("status") in {"completed", "failed", "stopped"}:
                break
            time.sleep(args.poll_seconds)

        if terminal_status.get("status") not in {"completed", "failed", "stopped"}:
            stop_deadline = time.monotonic() + args.post_stream_timeout_seconds
            while time.monotonic() < stop_deadline:
                terminal_status = _request_json(f"{api_url}/v1/streams/{stream_id}")
                if terminal_status.get("status") in {"completed", "failed", "stopped"}:
                    break
                time.sleep(0.5)

        _stop_process(publisher)
        publisher_return_code = publisher.returncode
        terminal_watermark = _watermark_snapshot(api_url, stream_id)
        terminal_payload = _export(api_url, stream_id)
        terminal_elapsed_s = time.monotonic() - publisher_started
        stream_metrics_response: dict[str, Any] = {}
        stream_metrics_error: str | None = None
        try:
            stream_metrics_response = _request_json(f"{api_url}/v1/streams/{stream_id}/metrics")
        except Exception as error:
            stream_metrics_error = f"{type(error).__name__}: {error}"[:500]
        stream_metrics = stream_metrics_response.get("metrics")
        if not isinstance(stream_metrics, dict):
            stream_metrics = None
        runtime_metrics_summary = _runtime_metrics_summary(stream_metrics)

        source_events = terminal_payload.get("events", [])
        captions = terminal_payload.get("captions", [])
        live_caption_latencies: list[dict[str, Any]] = []
        for caption in captions:
            if not isinstance(caption, dict):
                continue
            first_seen_s = caption_first_seen.get(_caption_key(caption))
            interval = caption.get("time_range", {})
            source_end_ms = interval.get("end_ms") if isinstance(interval, dict) else None
            if (
                first_seen_s is None
                or first_seen_s > publisher_elapsed_s
                or not isinstance(source_end_ms, (int, float))
            ):
                continue
            live_caption_latencies.append(
                {
                    "status": caption.get("status"),
                    "source_start_ms": interval.get("start_ms"),
                    "source_end_ms": source_end_ms,
                    "first_observed_elapsed_s": round(first_seen_s, 3),
                    "observed_output_lag_ms": round(first_seen_s * 1000 - source_end_ms),
                    "poll_resolution_ms": round(args.poll_seconds * 1000),
                    "caption_ru": caption.get("caption_ru", ""),
                }
            )
        live_caption_lag_ms = [
            int(item["observed_output_lag_ms"]) for item in live_caption_latencies
        ]
        event_latencies: list[dict[str, Any]] = []
        for event in source_events:
            updated = event.get("updated_at_utc")
            try:
                updated_at = datetime.fromisoformat(updated)
                wall_elapsed = (updated_at - publisher_started_utc).total_seconds()
            except (TypeError, ValueError):
                wall_elapsed = None
            event_latencies.append(
                {
                    "level": event.get("level"),
                    "kind": event.get("kind"),
                    "start_ms": event.get("start_ms"),
                    "end_ms": event.get("end_ms"),
                    "wall_elapsed_since_publish_s": (
                        round(wall_elapsed, 3) if wall_elapsed is not None else None
                    ),
                    "source_end_ms": event.get("end_ms"),
                    "approx_output_lag_ms": (
                        round(wall_elapsed * 1000 - event.get("end_ms", 0))
                        if wall_elapsed is not None
                        else None
                    ),
                    "updated_at_utc": updated,
                }
            )
        pre_end_samples = [s for s in samples if s["publisher_elapsed_s"] <= publisher_elapsed_s]
        live_event_latencies = [
            item
            for item in event_latencies
            if item["wall_elapsed_since_publish_s"] is not None
            and item["wall_elapsed_since_publish_s"] <= publisher_elapsed_s
        ]
        first_caption_sample = next(
            (s["publisher_elapsed_s"] for s in samples if s["caption_count"] > 0), None
        )
        counts_by_level: dict[str, int] = {}
        for event in source_events:
            level = event.get("level", "?")
            counts_by_level[level] = counts_by_level.get(level, 0) + 1
        report = {
            "schema_version": 1,
            "runtime_target": (
                "CPU, local RTSP loopback, real Tears of Steel A/V, "
                + ("Qwen narrator requested with L3" if "L3" in levels else "L3/Qwen disabled")
            ),
            "created_at_utc": datetime.now(UTC).isoformat(),
            "source": str(source),
            "source_duration_ms": 90_000,
            "input_looped": args.loop_input,
            "levels": levels,
            "threads": args.threads,
            "window_ms": args.window_ms,
            "poll_seconds": args.poll_seconds,
            "requested_live_seconds": args.live_seconds,
            "publisher_return_code": publisher_return_code,
            "publisher_elapsed_s": round(publisher_elapsed_s, 3),
            "stop_requested_elapsed_s": round(stop_requested_elapsed_s, 3),
            "stop_response_status": stop_response.get("status"),
            "terminal_elapsed_since_publish_s": round(terminal_elapsed_s, 3),
            "post_stop_wait_s": round(terminal_elapsed_s - stop_requested_elapsed_s, 3),
            "terminal_status": terminal_status,
            "pre_stop_caption_count": pre_stop_caption_count,
            "pre_stop_refine_l3_result": pre_stop_refine_result,
            "pre_stop_watermark": pre_stop_watermark,
            "pre_stop_last_sample": pre_end_samples[-1] if pre_end_samples else None,
            "first_caption_elapsed_since_publish_s": first_caption_sample,
            "first_caption_after_stop_s": (
                round(first_caption_sample - stop_requested_elapsed_s, 3)
                if first_caption_sample is not None
                else None
            ),
            "terminal_watermark": terminal_watermark,
            "stream_metrics": stream_metrics,
            "runtime_metrics_summary": runtime_metrics_summary,
            "stream_metrics_error": stream_metrics_error,
            "event_count_by_level": counts_by_level,
            "live_event_count_by_level": {
                level: sum(1 for item in live_event_latencies if item["level"] == level)
                for level in ("L1", "L2", "L3")
            },
            "live_event_output_lag_ms": {
                level: [
                    item["approx_output_lag_ms"]
                    for item in live_event_latencies
                    if item["level"] == level
                ]
                for level in ("L1", "L2", "L3")
            },
            "caption_count": len(captions),
            "live_caption_count": len(live_caption_latencies),
            "post_stop_caption_count": len(captions) - len(live_caption_latencies),
            "live_caption_output_lag_ms": live_caption_latencies,
            "live_caption_output_lag_summary_ms": _latency_summary(live_caption_lag_ms),
            "captions": captions,
            "event_latency_samples": event_latencies,
            "watermark_samples": samples,
            "api_error": terminal_status.get("error"),
        }
        (output_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (output_dir / "events_live.json").write_text(
            json.dumps(source_events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (output_dir / "captions_live.json").write_text(
            json.dumps(captions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in (
                        "runtime_target",
                        "publisher_elapsed_s",
                        "terminal_elapsed_since_publish_s",
                        "terminal_status",
                        "pre_stop_caption_count",
                        "pre_stop_refine_l3_result",
                        "pre_stop_last_sample",
                        "event_count_by_level",
                        "caption_count",
                        "live_caption_count",
                        "post_stop_caption_count",
                        "live_caption_output_lag_summary_ms",
                        "live_event_count_by_level",
                        "first_caption_after_stop_s",
                        "post_stop_wait_s",
                        "runtime_metrics_summary",
                    )
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if terminal_status.get("status") in {"completed", "stopped"} else 2
    finally:
        _stop_process(publisher)
        _stop_process(api)
        _stop_process(mediamtx)
        publisher_log.close()
        api_log.close()
        media_log.close()


if __name__ == "__main__":
    sys.exit(main())
