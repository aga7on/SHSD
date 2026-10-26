"""Run bounded 2x/5x RTSP source smokes against the local SHSD API.

Requires FFmpeg and MediaMTX executables. This is an integration benchmark,
not a unit test: it publishes synthetic, clocked A/V and samples stream
watermarks while the API is under an optional injected memory-pressure limit.
Each stream has distinct, time-varying audio/video input; every run gets a fresh
embedding cache unless the caller explicitly supplies one.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(
    url: str, *, method: str = "GET", body: dict[str, Any] | None = None
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object from {url}")
    return value


def wait_for_port(port: int, process: subprocess.Popen[Any], timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"process exited before port {port} became ready")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"port {port} did not become ready")


def wait_for_api(base_url: str, process: subprocess.Popen[Any], timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("SHSD API process exited before becoming ready")
        try:
            request_json(f"{base_url}/v1/streams")
            return
        except (OSError, urllib.error.URLError, TimeoutError):
            time.sleep(0.25)
    raise TimeoutError("SHSD API did not become ready")


def stop_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def source_snapshot(base_url: str, stream_id: str) -> dict[str, Any]:
    request_started = time.perf_counter()
    watermark_record = request_json(
        f"{base_url}/v1/streams/{stream_id}/watermarks?include_issues=false"
    )
    request_latency_ms = (time.perf_counter() - request_started) * 1000
    record = watermark_record.get("watermarks")
    snapshot = record.get("watermarks") if isinstance(record, dict) else None
    return {
        "at_utc": datetime.now(UTC).isoformat(),
        "api_latency_ms": round(request_latency_ms, 3),
        "status": watermark_record.get("status"),
        "epoch": watermark_record.get("epoch"),
        "watermarks": snapshot if isinstance(snapshot, dict) else {},
    }


def capture_ms(snapshot: dict[str, Any]) -> int:
    watermarks = snapshot.get("watermarks")
    return int(watermarks.get("C", 0)) if isinstance(watermarks, dict) else 0


def run_scale(
    *,
    count: int,
    base_url: str,
    ffmpeg: str,
    rtsp_port: int,
    threads: int,
    vision_profile: str,
    sampling_profile: str,
    window_ms: int,
    duration_seconds: float,
    capture_timeout_seconds: float,
    stop_timeout_seconds: float,
    output_dir: Path,
) -> dict[str, Any]:
    publishers: list[tuple[subprocess.Popen[Any], Any]] = []
    stream_ids: list[str] = []
    timeline: dict[str, list[dict[str, Any]]] = {}
    start = time.monotonic()
    try:
        for index in range(1, count + 1):
            stream_id = f"rtsp-{count}x-{index:02d}"
            path = f"shsd-{count}x-{index:02d}"
            log_path = output_dir / f"publisher-{count}x-{index:02d}.log"
            log = log_path.open("wb")
            command = [
                ffmpeg,
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "warning",
                "-re",
                "-f",
                "lavfi",
                "-i",
                (
                    "testsrc2=size=320x180:rate=10,"
                    f"drawbox=x={index * 12}:y=0:w=6:h=180:color=red:t=fill"
                ),
                "-re",
                "-f",
                "lavfi",
                "-i",
                f"aevalsrc=0.2*sin(2*PI*({220 + index * 25}+4*t)*t):s=16000",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-tune",
                "zerolatency",
                "-pix_fmt",
                "yuv420p",
                "-g",
                "20",
                "-c:a",
                "aac",
                "-b:a",
                "32k",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "rtsp",
                "-rtsp_transport",
                "tcp",
                f"rtsp://127.0.0.1:{rtsp_port}/{path}",
            ]
            publisher = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            publishers.append((publisher, log))
            stream_ids.append(stream_id)
            time.sleep(0.4)
            request_json(
                f"{base_url}/v1/streams",
                method="POST",
                body={
                    "source": f"rtsp://127.0.0.1:{rtsp_port}/{path}",
                    "stream_id": stream_id,
                    "levels": ["L0", "L1", "L2"],
                    "threads": threads,
                    "vision_profile": vision_profile,
                    "sampling_profile": sampling_profile,
                    "window_ms": window_ms,
                    "prefetch_overflow_policy": "drop_oldest",
                    "prefetch_capacity": 8,
                },
            )
            timeline[stream_id] = []

        capture_deadline = time.monotonic() + capture_timeout_seconds
        capture_ready = False
        capture_wait_seconds = 0.0
        while time.monotonic() < capture_deadline:
            current = {
                stream_id: source_snapshot(base_url, stream_id)
                for stream_id in stream_ids
            }
            for stream_id, snapshot in current.items():
                timeline[stream_id].append(snapshot)
            if all(capture_ms(snapshot) > 0 for snapshot in current.values()):
                capture_ready = True
                break
            if all(
                capture_ms(snapshot) > 0
                or snapshot["status"] in {"failed", "completed"}
                for snapshot in current.values()
            ):
                capture_ready = all(capture_ms(snapshot) > 0 for snapshot in current.values())
                break
            time.sleep(5)
        capture_wait_seconds = round(time.monotonic() - start, 3)

        deadline = time.monotonic() + duration_seconds
        if capture_ready:
            while time.monotonic() < deadline:
                for stream_id in stream_ids:
                    timeline[stream_id].append(source_snapshot(base_url, stream_id))
                time.sleep(1)

        for stream_id in stream_ids:
            try:
                status = request_json(f"{base_url}/v1/streams/{stream_id}")
                if status.get("status") in {"queued", "running", "stopping"}:
                    request_json(f"{base_url}/v1/streams/{stream_id}", method="DELETE")
            except urllib.error.HTTPError as error:
                if error.code != 409:
                    raise

        stop_started = time.monotonic()
        stop_deadline = stop_started + stop_timeout_seconds
        final: dict[str, Any] = {}
        while time.monotonic() < stop_deadline:
            final = {
                stream_id: request_json(f"{base_url}/v1/streams/{stream_id}")
                for stream_id in stream_ids
            }
            if all(
                item.get("status") in {"stopped", "completed", "failed"}
                for item in final.values()
            ):
                break
            time.sleep(0.25)
        stop_wait_seconds = round(time.monotonic() - stop_started, 3)
        all_streams_terminal = len(final) == len(stream_ids) and all(
            item.get("status") in {"stopped", "completed", "failed"}
            for item in final.values()
        )
        detail: dict[str, Any] = {}
        for stream_id in stream_ids:
            metrics_response = request_json(f"{base_url}/v1/streams/{stream_id}/metrics")
            watermarks_response = request_json(
                f"{base_url}/v1/streams/{stream_id}/watermarks?include_issues=false"
            )
            detail[stream_id] = {
                "status": final.get(stream_id, {}).get("status"),
                "error": final.get(stream_id, {}).get("error"),
                "watermarks": watermarks_response.get("watermarks"),
                "metrics": metrics_response.get("metrics"),
                "snapshots": timeline[stream_id],
            }
        return {
            "stream_count": count,
            "capture_ready": capture_ready,
            "capture_wait_seconds": capture_wait_seconds,
            "requested_live_seconds": duration_seconds,
            "stop_wait_seconds": stop_wait_seconds,
            "all_streams_terminal": all_streams_terminal,
            "wall_seconds": round(time.monotonic() - start, 3),
            "streams": detail,
        }
    finally:
        for publisher, log in publishers:
            stop_process(publisher)
            log.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mediamtx", required=True, help="Path to mediamtx executable")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument(
        "--shsd", default=str(ROOT / ".venv" / "Scripts" / "shsd.exe")
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "benchmarks" / "reports" / "live_rtsp_priority_smoke",
    )
    parser.add_argument("--duration-seconds", type=float, default=25)
    parser.add_argument("--window-ms", type=int, default=5_000)
    parser.add_argument(
        "--threads",
        type=int,
        default=1,
        help="CPU threads per shared embedding provider (default: 1)",
    )
    parser.add_argument(
        "--embedding-concurrency",
        type=int,
        default=1,
        help="maximum concurrent calls to the shared embedding model (default: 1)",
    )
    parser.add_argument(
        "--sampling-profile",
        choices=("standard", "adaptive"),
        default="standard",
        help="audio/video embedding admission profile passed to each API stream",
    )
    parser.add_argument(
        "--vision-profile",
        choices=("standard", "compact"),
        default="standard",
        help="image embedding detail profile passed to each API stream",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="embedding cache path; defaults to a fresh cache for this run",
    )
    parser.add_argument("--capture-timeout-seconds", type=float, default=120)
    parser.add_argument("--stop-timeout-seconds", type=float, default=120)
    parser.add_argument("--memory-limit-bytes", type=int, default=1)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    if args.embedding_concurrency < 1:
        parser.error("--embedding-concurrency must be positive")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("run_%Y%m%dT%H%M%S%f")
    state_dir = output_dir / "state" / run_id
    cache_dir = args.cache_dir.resolve() if args.cache_dir else output_dir / "cache" / run_id

    rtsp_port, api_port = free_port(), free_port()
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
    api_url = f"http://127.0.0.1:{api_port}"
    media_log = (output_dir / "mediamtx.log").open("wb")
    api_log = (output_dir / "api.log").open("wb")
    mediamtx: subprocess.Popen[Any] | None = None
    api: subprocess.Popen[Any] | None = None
    try:
        mediamtx = subprocess.Popen(
            [args.mediamtx, str(config_path)],
            cwd=output_dir,
            stdout=media_log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        wait_for_port(rtsp_port, mediamtx)
        environment = os.environ.copy()
        environment["SHSD_MEMORY_LIMIT_BYTES"] = str(args.memory_limit_bytes)
        api = subprocess.Popen(
            [
                args.shsd,
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
                "--embedding-concurrency",
                str(args.embedding_concurrency),
            ],
            cwd=ROOT,
            env=environment,
            stdout=api_log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        wait_for_api(api_url, api)
        scenarios: dict[str, Any] = {}
        for count in (2, 5):
            try:
                scenarios[str(count)] = run_scale(
                    count=count,
                    base_url=api_url,
                    ffmpeg=args.ffmpeg,
                    rtsp_port=rtsp_port,
                    threads=args.threads,
                    sampling_profile=args.sampling_profile,
                    vision_profile=args.vision_profile,
                    window_ms=args.window_ms,
                    duration_seconds=args.duration_seconds,
                    capture_timeout_seconds=args.capture_timeout_seconds,
                    stop_timeout_seconds=args.stop_timeout_seconds,
                    output_dir=output_dir,
                )
            except Exception as error:
                scenarios[str(count)] = {
                    "status": "harness_error",
                    "error": f"{type(error).__name__}: {error}",
                }
        report = {
            "schema_version": 1,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "runtime_target": "local RTSP loopback; synthetic live A/V",
            "memory_limit_bytes": args.memory_limit_bytes,
            "duration_seconds_per_scenario": args.duration_seconds,
            "threads_per_stream": args.threads,
            "embedding_concurrency": args.embedding_concurrency,
            "window_ms": args.window_ms,
            "sampling_profile": args.sampling_profile,
            "vision_profile": args.vision_profile,
            "cache_dir": str(cache_dir),
            "cache_isolated_per_run": args.cache_dir is None,
            "capture_timeout_seconds": args.capture_timeout_seconds,
            "stop_timeout_seconds": args.stop_timeout_seconds,
            "scenarios": scenarios,
        }
        (output_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return (
            0
            if all(
                item.get("capture_ready") and item.get("all_streams_terminal")
                for item in scenarios.values()
            )
            else 2
        )
    finally:
        if api is not None:
            stop_process(api)
        if mediamtx is not None:
            stop_process(mediamtx)
        api_log.close()
        media_log.close()


if __name__ == "__main__":
    sys.exit(main())
