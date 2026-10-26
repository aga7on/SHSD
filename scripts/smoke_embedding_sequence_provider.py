"""Exercise production EmbeddingProvider sequence features on local fixtures."""

from __future__ import annotations

import argparse
import json
import os
import platform
from datetime import UTC, datetime
from pathlib import Path
from tempfile import gettempdir
from typing import Any

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np

from shsd.embeddings.provider import (
    PREPROCESS_VERSION,
    EmbeddingProvider,
    _load_video_sample,
)

ROOT = Path(__file__).resolve().parents[1]


def _read_audio(path: Path, *, target_samples: int) -> np.ndarray:
    import av

    with av.open(str(path), mode="r") as container:
        if not container.streams.audio:
            raise ValueError(f"fixture has no audio stream: {path}")
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=16_000)
        parts: list[np.ndarray] = []
        sample_count = 0
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                part = np.asarray(converted.to_ndarray(), dtype=np.float32).reshape(-1)
                parts.append(part)
                sample_count += part.size
                if sample_count >= target_samples:
                    break
            if sample_count >= target_samples:
                break
    if not parts:
        raise ValueError(f"fixture decoded no audio: {path}")
    return np.concatenate(parts)[:target_samples]


def _summary(record: Any) -> dict[str, Any]:
    result = record.to_dict()
    result["token_embeddings_finite"] = bool(np.isfinite(record.token_embeddings).all())
    result["active_tokens"] = int(record.attention_mask.sum())
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "benchmarks" / "reports" / "bridge_f10" / "production_sequence_smoke.json",
    )
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")

    lock = json.loads((ROOT / "models.lock.json").read_text(encoding="utf-8"))
    model = lock["models"]["embeddinggemma2"]
    audio_path = ROOT / "tests" / "fixtures" / "media" / "audio_speech_ru.wav"
    video_path = ROOT / "tests" / "fixtures" / "media" / "video_scene_cuts_8s.mp4"
    audio = _read_audio(audio_path, target_samples=80_000)
    frames, pts_ms, metadata = _load_video_sample(
        video_path,
        interval_ms=(0, 5000),
        max_frames=4,
    )
    image_rgb = np.asarray(frames[0].convert("RGB"))

    provider = EmbeddingProvider(
        model,
        ROOT / "models",
        cache_dir=Path(gettempdir()) / "shsd-sequence-feature-smoke-cache",
        threads=args.threads,
        enabled_modalities={"audio", "image", "video"},
    )
    records = {
        "IMAGE": provider.encode_frame_features(image_rgb, pts_ms[0]),
        "AUDIO": provider.encode_audio_features(audio, (0, 5000)),
        "VIDEO": provider.encode_video_features(
            video_path,
            (0, 5000),
            max_frames=4,
        ),
        "AV": provider.encode_joint_features(
            audio,
            video_path,
            (0, 5000),
            max_frames=4,
        ),
    }

    for mode, record in records.items():
        if not record.token_embeddings.size or not np.isfinite(record.token_embeddings).all():
            raise RuntimeError(f"{mode}: invalid sequence features")
        if record.attention_mask.shape != (record.token_embeddings.shape[0],):
            raise RuntimeError(f"{mode}: token and attention-mask lengths differ")
    for mode in ("VIDEO", "AV"):
        record = records[mode]
        if record.frame_pts_ms != pts_ms:
            raise RuntimeError(f"{mode}: sampled PTS were not preserved")
        if record.video_metadata != metadata:
            raise RuntimeError(f"{mode}: video timestamp metadata changed")
    if records["IMAGE"].frame_pts_ms != (pts_ms[0],):
        raise RuntimeError("IMAGE: source frame PTS were not preserved")

    report = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "passed",
        "network_disabled": True,
        "host": {"os": platform.platform(), "cpu": platform.processor()},
        "model_revision": model["revision"],
        "preprocess_version": PREPROCESS_VERSION,
        "threads": args.threads,
        "input": {
            "video_fixture": str(video_path.relative_to(ROOT)),
            "audio_fixture": str(audio_path.relative_to(ROOT)),
            "interval_ms": [0, 5000],
            "frame_pts_ms": list(pts_ms),
            "video_metadata": metadata,
        },
        "modes": {mode: _summary(record) for mode, record in records.items()},
        "scope": (
            "Production provider exposes unpooled sequence tokens, masks, and sampled source PTS. "
            "This verifies interface transport only, not learned bridge quality or realtime."
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"status: {report['status']}")
    print(f"json: {args.report}")
    for mode, details in report["modes"].items():
        print(
            f"{mode}: tokens={details['token_embeddings_shape']} latency_ms={details['latency_ms']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
