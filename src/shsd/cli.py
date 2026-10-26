"""Command-line entry point for the SHSD package foundation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from shsd import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser and currently available replay command."""
    parser = argparse.ArgumentParser(
        prog="shsd",
        description="Streaming Hierarchical Semantic Decoder (CPU-first PoC).",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="show the installed version and exit",
    )
    subparsers = parser.add_subparsers(dest="command")
    replay_parser = subparsers.add_parser(
        "replay",
        description="Demultiplex a local media file in fast or clock-paced mode.",
        allow_abbrev=False,
    )
    replay_parser.add_argument("source", type=Path, help="local MP4, MKV, or media file")
    replay_modes = replay_parser.add_mutually_exclusive_group(required=True)
    replay_modes.add_argument(
        "--fast",
        dest="mode",
        action="store_const",
        const="fast",
        help="read as fast as possible",
    )
    replay_modes.add_argument(
        "--simulate-realtime",
        dest="mode",
        action="store_const",
        const="simulate_realtime",
        help="pace packets by source media time",
    )
    replay_parser.add_argument("--speed", type=float, default=1.0, help="media speed multiplier")
    replay_parser.add_argument("--stream-id", default=None, help="override the generated stream ID")

    analyze_parser = subparsers.add_parser(
        "analyze",
        description="Analyze local media with pinned CPU embeddings and emit evidence JSONL.",
        allow_abbrev=False,
    )
    analyze_parser.add_argument(
        "source",
        help="local media file or a PyAV-readable URL (for example RTSP or HTTP)",
    )
    analyze_parser.add_argument(
        "--levels",
        default="L0,L1",
        help="comma-separated output levels (L0,L1,L2,L3)",
    )
    analyze_parser.add_argument("--cpu-only", action="store_true", help="use CPU inference")
    analyze_parser.add_argument("--offline", action="store_true", help="disable HF network access")
    analyze_parser.add_argument("--threads", type=int, default=4)
    analyze_parser.add_argument("--window-seconds", type=float, default=5.0)
    analyze_parser.add_argument(
        "--prefetch-overflow-policy",
        choices=("block", "drop_newest", "drop_oldest"),
        default=None,
        help="queue overflow behavior (defaults to block for files and drop_oldest for RTSP)",
    )
    analyze_parser.add_argument(
        "--prefetch-capacity",
        type=int,
        default=None,
        help="set both bounded modality queue capacities (defaults: audio 64, video 8)",
    )
    analyze_parser.add_argument("--minimum-similarity", type=float, default=0.60)
    analyze_parser.add_argument("--minimum-margin", type=float, default=0.05)
    analyze_parser.add_argument("--top-k", type=int, default=3)
    analyze_parser.add_argument(
        "--iterative-axis",
        default=None,
        help="opt in to one bounded Qwen proposal pass for a selected axis",
    )
    analyze_parser.add_argument(
        "--speech",
        action="store_true",
        help="opt in to the bounded local GigaAM-v3 CPU ASR worker",
    )
    analyze_parser.add_argument(
        "--sampling-profile",
        choices=("standard", "adaptive"),
        default="standard",
        help="select fixed-stride sampling or activity-driven sampling with a heartbeat",
    )
    analyze_parser.add_argument(
        "--vision-profile",
        choices=("standard", "compact"),
        default="standard",
        help="select full 280-token or compact 140-token image embeddings",
    )
    analyze_parser.add_argument(
        "--narrator-mode",
        choices=("qwen", "template"),
        default="qwen",
        help="select Qwen generation or the source-only template baseline for L3",
    )
    analyze_parser.add_argument("--stream-id", default=None)
    analyze_parser.add_argument("--event-db", default=":memory:")
    analyze_parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="override the local embedding cache directory",
    )
    analyze_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write JSONL to this file; defaults to stdout",
    )
    serve_parser = subparsers.add_parser(
        "serve",
        description="Serve local SHSD streams over REST and WebSocket.",
        allow_abbrev=False,
    )
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--data-dir", type=Path, default=None)
    serve_parser.add_argument("--models-dir", type=Path, default=None)
    serve_parser.add_argument("--cache-dir", type=Path, default=None)
    serve_parser.add_argument(
        "--embedding-concurrency",
        type=int,
        default=1,
        help="maximum concurrent CPU calls to the shared embedding model (default: 1)",
    )
    return parser


def _run_replay(
    source: Path,
    mode: Literal["fast", "simulate_realtime"],
    speed: float,
    stream_id: str | None,
) -> int:
    from shsd.ingest.pipeline import replay_into_bounded_ring

    report = replay_into_bounded_ring(
        source,
        mode=mode,
        speed=speed,
        stream_id=stream_id or source.stem,
    )
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the available CLI command or display top-level help."""
    parser = build_parser()
    parsed = parser.parse_args(argv)
    if parsed.command == "replay":
        if parsed.speed <= 0:
            parser.error("replay --speed must be positive")
        return _run_replay(parsed.source, parsed.mode, parsed.speed, parsed.stream_id)
    if parsed.command == "analyze":
        if not parsed.cpu_only:
            parser.error("analyze currently supports CPU inference only; pass --cpu-only")
        if parsed.threads < 1 or parsed.window_seconds <= 0 or parsed.top_k < 1:
            parser.error("threads, window-seconds, and top-k must be positive")
        if parsed.prefetch_capacity is not None and parsed.prefetch_capacity < 1:
            parser.error("analyze --prefetch-capacity must be positive")
        window_ms = round(parsed.window_seconds * 1000)
        if window_ms < 250:
            parser.error("analyze --window-seconds must be at least 0.25")
        levels = frozenset(item.strip() for item in parsed.levels.split(",") if item.strip())
        if not levels or not levels.issubset({"L0", "L1", "L2", "L3"}):
            parser.error("analyze --levels accepts L0, L1, L2, and/or L3")
        if not -1 <= parsed.minimum_similarity <= 1:
            parser.error("analyze --minimum-similarity must be between -1 and 1")
        if not 0 <= parsed.minimum_margin <= 2:
            parser.error("analyze --minimum-margin must be between 0 and 2")
        return _run_analyze(parsed, levels, window_ms)
    if parsed.command == "serve":
        if not 1 <= parsed.port <= 65_535:
            parser.error("serve --port must be between 1 and 65535")
        if parsed.embedding_concurrency < 1:
            parser.error("serve --embedding-concurrency must be positive")
        return _run_serve(parsed)
    if parsed.command is None:
        parser.print_help()
    return 0


def _run_analyze(parsed: argparse.Namespace, levels: frozenset[str], window_ms: int) -> int:
    import os
    import sys
    from datetime import UTC, datetime

    from shsd.analyze import analyze_media, encode_jsonl
    from shsd.models.artifacts import MissingModelFiles
    from shsd.semantic.matcher import MatchPolicy

    root = Path(__file__).resolve().parents[2]
    lock = json.loads((root / "models.lock.json").read_text(encoding="utf-8"))
    if parsed.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    source: Path | str
    if "://" in parsed.source:
        source = parsed.source
    else:
        source = Path(parsed.source).expanduser().resolve()
    live_source = isinstance(source, str) and urlsplit(source).scheme.lower() in {
        "rtsp",
        "rtsps",
    }
    if live_source and parsed.prefetch_overflow_policy == "block":
        print(
            "live RTSP sources require --prefetch-overflow-policy drop_newest or drop_oldest",
            file=sys.stderr,
        )
        return 2
    source_name = source.stem if isinstance(source, Path) else Path(urlsplit(source).path).stem
    stream_id = parsed.stream_id or (
        f"{source_name}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    )
    if parsed.output is not None:
        parsed.output.parent.mkdir(parents=True, exist_ok=True)
        output_stream = parsed.output.open("w", encoding="utf-8", newline="\n")
    else:
        output_stream = sys.stdout

    def emit(record: dict[str, object]) -> None:
        output_stream.write(encode_jsonl(record) + "\n")
        output_stream.flush()
        if record.get("record_type") == "watermark":
            watermarks = record["watermarks"]
            backlog = record["backlog_ms"]
            if isinstance(watermarks, dict) and isinstance(backlog, dict):
                cursors = watermarks.get("R", {})
                if isinstance(cursors, dict):
                    print(
                        "progress "
                        f"C={watermarks.get('C', 0)} E={watermarks.get('E', 0)} "
                        f"R1={cursors.get('L1', 0)} R2={cursors.get('L2', 0)} "
                        f"R3={cursors.get('L3', 0)} backlog={backlog}",
                        file=sys.stderr,
                        flush=True,
                    )

    try:
        analyze_media(
            source,
            lock["models"]["embeddinggemma2"],
            root / "models",
            stream_id=stream_id,
            threads=parsed.threads,
            window_ms=window_ms,
            policy=MatchPolicy(
                minimum_similarity=parsed.minimum_similarity,
                minimum_margin=parsed.minimum_margin,
                top_k=parsed.top_k,
            ),
            levels=levels,
            cache_dir=parsed.cache_dir,
            event_database=parsed.event_db,
            emit=emit,
            iterative_axis=parsed.iterative_axis,
            speech_enabled=parsed.speech,
            narrator_mode=parsed.narrator_mode,
            sampling_profile=parsed.sampling_profile,
            vision_profile=parsed.vision_profile,
            prefetch_overflow_policy=parsed.prefetch_overflow_policy,
            prefetch_capacity=parsed.prefetch_capacity,
        )
    except MissingModelFiles as error:
        print(f"model unavailable: {error}", file=sys.stderr)
        if parsed.output is not None:
            output_stream.close()
        return 2
    except Exception:
        if parsed.output is not None:
            output_stream.close()
        raise
    if parsed.output is not None:
        output_stream.close()
        print(f"JSONL timeline saved to {parsed.output.resolve()}", file=sys.stderr)
    return 0


def _run_serve(parsed: argparse.Namespace) -> int:
    import sys

    try:
        import uvicorn

        from shsd.api.app import create_app
    except ImportError:
        print(
            "API dependencies are missing; install SHSD with `pip install -e '.[api]'`.",
            file=sys.stderr,
        )
        return 2

    root = Path(__file__).resolve().parents[2]
    app = create_app(
        root=root,
        data_dir=parsed.data_dir or Path.cwd() / "runs" / "shsd",
        models_dir=parsed.models_dir or root / "models",
        cache_dir=parsed.cache_dir,
        embedding_concurrency=parsed.embedding_concurrency,
    )
    uvicorn.run(app, host=parsed.host, port=parsed.port, log_level="info")
    return 0
