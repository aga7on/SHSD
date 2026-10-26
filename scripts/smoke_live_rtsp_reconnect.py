"""Exercise API recovery when an RTSP publisher drops and returns."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmark_live_rtsp_priority import (
    free_port,
    request_json,
    source_snapshot,
    stop_process,
    wait_for_api,
    wait_for_port,
)

ROOT = Path(__file__).resolve().parents[1]


def start_publisher(ffmpeg: str, url: str, log_path: Path) -> tuple[subprocess.Popen[Any], Any]:
    log = log_path.open("wb")
    process = subprocess.Popen(
        [
            ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "warning",
            "-re",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=10",
            "-re",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000",
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
            url,
        ],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return process, log


def wait_for_state(
    base_url: str,
    stream_id: str,
    predicate: Any,
    *,
    timeout_seconds: float,
    label: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = request_json(f"{base_url}/v1/streams/{stream_id}")
        if predicate(latest):
            return latest
        time.sleep(0.2)
    raise TimeoutError(f"timed out waiting for {label}; latest state: {latest}")


def wait_for_capture(
    base_url: str,
    stream_id: str,
    *,
    epoch: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = source_snapshot(base_url, stream_id)
        if (
            latest.get("epoch") == epoch
            and latest.get("status") == "running"
            and capture_ms(latest) > 0
        ):
            return latest
        if latest.get("status") in {"failed", "completed"}:
            raise RuntimeError(f"stream ended before reconnect capture: {latest}")
        time.sleep(0.5)
    raise TimeoutError(f"timed out waiting for epoch {epoch} capture: {latest}")


def capture_ms(snapshot: dict[str, Any]) -> int:
    watermarks = snapshot.get("watermarks")
    return int(watermarks.get("C", 0)) if isinstance(watermarks, dict) else 0


def run_smoke(
    *,
    mediamtx_path: str,
    ffmpeg_path: str,
    shsd_path: str,
    output_dir: Path,
    capture_timeout_seconds: float,
    terminal_timeout_seconds: float,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    state_dir = output_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
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
    base_url = f"http://127.0.0.1:{api_port}"
    rtsp_url = f"rtsp://127.0.0.1:{rtsp_port}/reconnect"
    mediamtx_log = (output_dir / "mediamtx.log").open("wb")
    api_log = (output_dir / "api.log").open("wb")
    media_server: subprocess.Popen[Any] | None = None
    api: subprocess.Popen[Any] | None = None
    publishers: list[tuple[subprocess.Popen[Any], Any]] = []
    stream_id = "rtsp-reconnect-smoke"
    timeline: list[dict[str, Any]] = []
    try:
        media_server = subprocess.Popen(
            [mediamtx_path, str(config_path)],
            cwd=output_dir,
            stdout=mediamtx_log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        wait_for_port(rtsp_port, media_server)
        first_publisher = start_publisher(ffmpeg_path, rtsp_url, output_dir / "publisher-1.log")
        publishers.append(first_publisher)
        time.sleep(0.5)

        environment = os.environ.copy()
        environment.pop("SHSD_MEMORY_LIMIT_BYTES", None)
        api = subprocess.Popen(
            [
                shsd_path,
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
                str(ROOT / ".cache"),
            ],
            cwd=ROOT,
            env=environment,
            stdout=api_log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        wait_for_api(base_url, api)
        request_json(
            f"{base_url}/v1/streams",
            method="POST",
            body={
                "source": rtsp_url,
                "stream_id": stream_id,
                "levels": ["L0", "L1"],
                "threads": 1,
                "window_ms": 5_000,
                "prefetch_overflow_policy": "drop_oldest",
                "prefetch_capacity": 8,
            },
        )

        first_capture = wait_for_capture(
            base_url,
            stream_id,
            epoch=0,
            timeout_seconds=capture_timeout_seconds,
        )
        timeline.append(first_capture)

        stop_process(first_publisher[0])
        reconnected_epoch = 1
        reconnect_state = wait_for_state(
            base_url,
            stream_id,
            lambda state: state.get("epoch", 0) >= reconnected_epoch,
            timeout_seconds=20,
            label="reconnect epoch",
        )
        timeline.append({"phase": "publisher_offline", **reconnect_state})

        second_publisher = start_publisher(
            ffmpeg_path, rtsp_url, output_dir / "publisher-2.log"
        )
        publishers.append(second_publisher)
        second_capture = wait_for_capture(
            base_url,
            stream_id,
            epoch=reconnected_epoch,
            timeout_seconds=capture_timeout_seconds,
        )
        timeline.append(second_capture)
        time.sleep(3)

        try:
            request_json(f"{base_url}/v1/streams/{stream_id}", method="DELETE")
        except urllib.error.HTTPError as error:
            if error.code != 409:
                raise
        final_state = wait_for_state(
            base_url,
            stream_id,
            lambda state: state.get("status") in {"stopped", "completed", "failed"},
            timeout_seconds=terminal_timeout_seconds,
            label="terminal stream state",
        )
        metrics_response = request_json(f"{base_url}/v1/streams/{stream_id}/metrics")
        result = {
            "schema_version": 1,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "runtime_target": "local MediaMTX RTSP with synthetic A/V publisher restart",
            "stream_id": stream_id,
            "source": "rtsp://127.0.0.1:<ephemeral>/reconnect",
            "initial_capture": first_capture,
            "after_disconnect": reconnect_state,
            "after_reconnect_capture": second_capture,
            "final_state": final_state,
            "metrics": metrics_response.get("metrics"),
            "timeline": timeline,
            "passed": (
                first_capture.get("epoch") == 0
                and reconnect_state.get("epoch", 0) >= 1
                and second_capture.get("epoch") == 1
                and final_state.get("status") == "stopped"
            ),
        }
        (output_dir / "report.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return result
    finally:
        for publisher, log in publishers:
            stop_process(publisher)
            log.close()
        if api is not None:
            stop_process(api)
        if media_server is not None:
            stop_process(media_server)
        api_log.close()
        mediamtx_log.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mediamtx", required=True, help="Path to mediamtx executable")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument(
        "--shsd", default=str(ROOT / ".venv" / "Scripts" / "shsd.exe")
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "benchmarks" / "reports" / "rtsp_reconnect_smoke_20261026",
    )
    parser.add_argument("--capture-timeout-seconds", type=float, default=60)
    parser.add_argument("--terminal-timeout-seconds", type=float, default=90)
    args = parser.parse_args()
    result = run_smoke(
        mediamtx_path=args.mediamtx,
        ffmpeg_path=args.ffmpeg,
        shsd_path=args.shsd,
        output_dir=args.output_dir.resolve(),
        capture_timeout_seconds=args.capture_timeout_seconds,
        terminal_timeout_seconds=args.terminal_timeout_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
