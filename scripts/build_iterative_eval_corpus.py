"""Build deterministic, window-aligned local A/B inputs from licensed audio assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import wave
from pathlib import Path
from typing import Any

import av
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_DIR = ROOT / "benchmarks" / "evaluation" / "iterative_speech_presence_natural"
SAMPLE_RATE = 16_000
WINDOW_MS = 5_000


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_mono_16k(path: Path) -> np.ndarray:
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    chunks: list[np.ndarray] = []
    with av.open(str(path), mode="r") as container:
        if not container.streams.audio:
            raise ValueError(f"audio stream missing: {path}")
        stream = container.streams.audio[0]
        for frame in container.decode(stream):
            chunks.extend(
                np.asarray(converted.to_ndarray(), dtype=np.int16).reshape(-1)
                for converted in resampler.resample(frame)
            )
        chunks.extend(
            np.asarray(converted.to_ndarray(), dtype=np.int16).reshape(-1)
            for converted in resampler.resample(None)
        )
    if not chunks:
        raise ValueError(f"audio decode returned no samples: {path}")
    return np.concatenate(chunks)


def _write_wav(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(np.asarray(samples, dtype="<i2").tobytes())


def build(eval_dir: Path) -> dict[str, Any]:
    manifest_path = eval_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("purpose") != "manual_evaluation_only":
        raise ValueError("manifest must explicitly identify evaluation-only data")
    assets = {asset["file"]: asset for asset in manifest["source_assets"]}
    decoded: dict[str, np.ndarray] = {}
    for filename, asset in assets.items():
        source_path = eval_dir / "sources" / filename
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        actual_hash = _sha256(source_path)
        if actual_hash != asset["sha256"]:
            raise ValueError(f"SHA-256 mismatch for {source_path}: {actual_hash}")
        decoded[filename] = _read_mono_16k(source_path)

    input_dir = eval_dir / "inputs"
    segment_rows: list[dict[str, object]] = []
    built_corpora: list[dict[str, object]] = []
    required_samples = SAMPLE_RATE * WINDOW_MS // 1000
    for corpus in manifest["corpora"]:
        corpus_parts: list[np.ndarray] = []
        corpus_labels = corpus["expected_candidate_id"]
        for index, segment in enumerate(corpus["segments"]):
            filename = segment["source_file"]
            if filename not in decoded:
                raise ValueError(f"unknown source asset {filename!r}")
            start_ms = int(segment["source_start_ms"])
            end_ms = int(segment["source_end_ms"])
            if start_ms < 0 or end_ms - start_ms != WINDOW_MS:
                raise ValueError("each source segment must be a non-negative 5-second interval")
            samples = decoded[filename]
            start_sample = start_ms * SAMPLE_RATE // 1000
            end_sample = end_ms * SAMPLE_RATE // 1000
            if end_sample > samples.size:
                raise ValueError(
                    f"segment {filename} [{start_ms},{end_ms}) exceeds decoded duration "
                    f"{samples.size * 1000 // SAMPLE_RATE} ms"
                )
            part = samples[start_sample:end_sample]
            if part.size != required_samples:
                raise ValueError(f"segment {filename} is not exactly five seconds")
            corpus_parts.append(part)
            segment_rows.append(
                {
                    "stream_id": corpus["stream_id"],
                    "axis_id": "speech_presence",
                    "expected_candidate_id": corpus_labels,
                    "corpus_file": corpus["file"],
                    "window_index": index,
                    "start_ms": index * WINDOW_MS,
                    "end_ms": (index + 1) * WINDOW_MS,
                    "source_file": filename,
                    "source_start_ms": start_ms,
                    "source_end_ms": end_ms,
                    "rationale": segment["rationale"],
                }
            )
        output = input_dir / corpus["file"]
        _write_wav(output, np.concatenate(corpus_parts))
        built_corpora.append(
            {
                "file": corpus["file"],
                "stream_id": corpus["stream_id"],
                "window_count": len(corpus_parts),
                "duration_ms": len(corpus_parts) * WINDOW_MS,
                "bytes": output.stat().st_size,
                "sha256": _sha256(output),
            }
        )

    segment_path = eval_dir / "expected_segments.jsonl"
    segment_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in segment_rows),
        encoding="utf-8",
    )
    result = {
        "schema_version": 1,
        "purpose": "manual_evaluation_only",
        "runtime_corpus_files": built_corpora,
        "expected_segments": len(segment_rows),
        "segments_path": str(segment_path.relative_to(ROOT)),
        "sample_rate": SAMPLE_RATE,
        "window_ms": WINDOW_MS,
    }
    result_path = eval_dir / "build_report.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR)
    args = parser.parse_args()
    print(json.dumps(build(args.eval_dir.resolve()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
