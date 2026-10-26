"""Run explicit, local-only CPU smoke checks for the pinned model artifacts."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shsd.models.artifacts import MissingModelFiles, verify_local_artifacts

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "models.lock.json"
DEFAULT_MODELS = ROOT / "models"
DEFAULT_REPORT = ROOT / "benchmarks" / "reports" / "model_smoke.json"


def _embedding_smoke(
    model: dict[str, Any], models_dir: Path, *, threads: int
) -> dict[str, Any]:
    import av
    import numpy as np

    from shsd.embeddings.provider import EmbeddingProvider
    from shsd.semantic.hypotheses import encode_profile_candidates, load_profiles

    verified = verify_local_artifacts("embeddinggemma2", model, models_dir)
    image = np.full((64, 96, 3), (46, 102, 128), dtype=np.uint8)
    local_audio = ROOT / "tests" / "fixtures" / "media" / "audio_speech_ru.wav"
    local_video = ROOT / "tests" / "fixtures" / "media" / "video_scene_cuts_8s.mp4"

    with tempfile.TemporaryDirectory(prefix="shsd-embedding-smoke-") as cache_dir:
        started = time.perf_counter()
        provider = EmbeddingProvider(
            model,
            models_dir,
            threads=threads,
            cache_dir=Path(cache_dir),
        )
        load_ms = (time.perf_counter() - started) * 1000
        profiles = load_profiles(
            ROOT / "configs" / "hypotheses",
            expected_model_revision=str(model["revision"]),
        )
        profile_vectors = {
            profile.profile_id: encode_profile_candidates(profile, provider)
            for profile in profiles
        }
        repeated_profile_vectors = {
            profile.profile_id: encode_profile_candidates(profile, provider)
            for profile in profiles
        }
        if any(
            not record.cache_hit
            for axes in repeated_profile_vectors.values()
            for records in axes.values()
            for record in records.values()
        ):
            raise RuntimeError("versioned hypothesis vectors were recomputed on a cache hit")

        with av.open(str(local_audio)) as container:
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=16_000)
            parts: list[np.ndarray] = []
            for frame in container.decode(audio=0):
                parts.extend(
                    np.asarray(converted.to_ndarray(), dtype=np.float32).reshape(-1)
                    for converted in resampler.resample(frame)
                )
            parts.extend(
                np.asarray(converted.to_ndarray(), dtype=np.float32).reshape(-1)
                for converted in resampler.resample(None)
            )
        audio = np.concatenate(parts)
        duration_ms = round(audio.size * 1000 / 16_000)
        candidates = ["Короткий локальный тестовый текст."]
        records = {
            "text": provider.encode_texts(candidates)[0],
            "image": provider.encode_frame(image, pts_ms=0),
            "audio": provider.encode_audio(audio, interval_ms=(0, duration_ms)),
            "video": provider.encode_video(local_video),
            "joint": provider.encode_joint(
                audio, local_video, interval_ms=(0, duration_ms)
            ),
        }
        repeated = {
            "text": provider.encode_texts(candidates)[0],
            "image": provider.encode_frame(image, pts_ms=0),
            "audio": provider.encode_audio(audio, interval_ms=(0, duration_ms)),
            "video": provider.encode_video(local_video),
            "joint": provider.encode_joint(
                audio, local_video, interval_ms=(0, duration_ms)
            ),
        }
        if any(
            not item.cache_hit
            or not np.allclose(
                records[modality].embedding, item.embedding, rtol=0.0, atol=1e-6
            )
            for modality, item in repeated.items()
        ):
            states = {
                modality: {
                    "cache_hit": item.cache_hit,
                    "max_abs_diff": float(
                        np.max(np.abs(records[modality].embedding - item.embedding))
                    ),
                }
                for modality, item in repeated.items()
            }
            raise RuntimeError(f"EmbeddingGemma disk cache did not reuse all vectors: {states}")

        same_image_later = provider.encode_frame(image, pts_ms=1)
        same_audio_later = provider.encode_audio(
            audio, interval_ms=(duration_ms, duration_ms * 2)
        )
        if (
            not same_image_later.cache_hit
            or same_image_later.window_id == records["image"].window_id
            or not same_audio_later.cache_hit
            or same_audio_later.window_id == records["audio"].window_id
        ):
            raise RuntimeError(
                "content cache reuse must preserve distinct source-window identities"
            )

        candidate_profiles = {
            profile.profile_id: {
                "fingerprint": profile.candidate_fingerprint(),
                "axes": len(profile.axes),
                "candidate_count": sum(len(axis.candidates) for axis in profile.axes),
                "encode_ms": round(
                    sum(
                        record.latency_ms
                        for axes in profile_vectors[profile.profile_id].values()
                        for record in axes.values()
                    ),
                    3,
                ),
                "cache_reuse_verified": True,
            }
            for profile in profiles
        }

        modalities: dict[str, Any] = {}
        for modality, record in records.items():
            if record.embedding_dim != 768 or not np.isfinite(record.embedding).all():
                raise RuntimeError(
                    f"EmbeddingGemma {modality} output is invalid: "
                    f"shape={record.embedding.shape}, "
                    f"finite={bool(np.isfinite(record.embedding).all())}"
                )
            modalities[modality] = {
                "shape": list(record.embedding.shape),
                "dtype": str(record.embedding.dtype),
                "finite": True,
                "norm": record.norm,
                "latency_ms": record.latency_ms,
                "cache_hit": record.cache_hit,
                "window_id": record.window_id,
                "interval_ms": list(record.interval_ms) if record.interval_ms else None,
            }
        return {
            "status": "passed",
            "revision": model["revision"],
            "device": str(provider.encoder.device),
            "dtype": str(provider.encoder.dtype),
            "threads": threads,
            "model_load_ms": round(load_ms, 3),
            "cache_reuse_verified": True,
            "same_content_reuses_vector_distinct_windows_verified": True,
            "candidate_profiles": candidate_profiles,
            "verified_files": verified,
            "modalities": modalities,
        }


def _qwen_smoke(
    model: dict[str, Any], models_dir: Path, *, threads: int, max_tokens: int
) -> dict[str, Any]:
    model_path = models_dir / "qwen3_0_6b" / model["file"]
    verified = verify_local_artifacts("qwen3_0_6b", model, models_dir)
    binary_dir = models_dir / "runtimes" / "llama_cpp" / "b11886" / "bin"
    llama_cli = binary_dir / "llama-cli.exe"
    if not llama_cli.is_file():
        message = (
            f"llama.cpp executable is missing: {llama_cli}. "
            "Fetch it explicitly with: python scripts/download_models.py --runtime llama_cpp"
        )
        raise MissingModelFiles(message)

    prompt = (
        "Опиши одним коротким предложением только эти факты: "
        "в кадре однотонный фон; аудио содержит синтетический тон 440 Гц."
    )
    template = ROOT / "configs" / "qwen3_nonthinking.jinja"
    command = [
        str(llama_cli),
        "--model",
        str(model_path),
        "--prompt",
        prompt,
        "--chat-template-file",
        str(template),
        "--jinja",
        "--single-turn",
        "--no-display-prompt",
        "--simple-io",
        "--log-disable",
        "--no-perf",
        "--threads",
        str(threads),
        "--ctx-size",
        "1024",
        "--predict",
        str(max_tokens),
        "--temp",
        "0",
        "--top-k",
        "1",
        "--seed",
        "7",
    ]
    started = time.perf_counter()
    result = subprocess.run(command, check=True, capture_output=True, timeout=900)
    latency_ms = (time.perf_counter() - started) * 1000
    raw_output = result.stdout.decode("utf-8", errors="replace")
    if prompt not in raw_output:
        raise RuntimeError("Qwen CLI output did not contain the submitted prompt")
    output = raw_output.rsplit(prompt, maxsplit=1)[1]
    output = re.split(r"\r?\n\s*\[ Prompt:", output, maxsplit=1)[0]
    output = re.split(r"\r?\n\s*Exiting\.\.\.", output, maxsplit=1)[0].strip()
    has_cyrillic = any("\u0400" <= char <= "\u04ff" for char in output)
    forbidden_output = ("Loading model...", "available commands:", "build      :", "model      :")
    if (
        not output
        or "<think>" in output
        or not has_cyrillic
        or any(marker in output for marker in forbidden_output)
    ):
        raise RuntimeError(
            f"Qwen non-thinking Russian smoke output failed validation: {output!r}"
        )
    version = subprocess.run(
        [str(llama_cli), "--version"], check=True, capture_output=True, timeout=30
    )
    version_text = version.stdout.decode("utf-8", errors="replace") + version.stderr.decode(
        "utf-8", errors="replace"
    )
    return {
        "status": "passed",
        "revision": model["revision"],
        "quantization": model["quantization"],
        "runtime": version_text.strip(),
        "device": "cpu",
        "threads": threads,
        "max_tokens": max_tokens,
        "latency_ms": round(latency_ms, 3),
        "verified_files": verified,
        "prompt": prompt,
        "output_ru": output,
    }


def _gigaam_smoke(
    model: dict[str, Any], models_dir: Path, *, threads: int
) -> dict[str, Any]:
    import torch
    import transformers.dynamic_module_utils as module_utils
    from transformers import AutoConfig, AutoModel

    model_dir = models_dir / "gigaam_v3_e2e_ctc"
    verified = verify_local_artifacts("gigaam_v3_e2e_ctc", model, models_dir)
    audio_path = ROOT / "tests" / "fixtures" / "media" / "audio_speech_ru.wav"
    if not audio_path.is_file():
        raise FileNotFoundError(f"Synthetic Russian speech fixture is missing: {audio_path}")

    torch.set_num_threads(threads)
    started = time.perf_counter()
    original_check_imports = module_utils.check_imports

    def check_imports_without_optional_diarization(filename: str) -> list[str]:
        imports = module_utils.get_imports(filename)
        missing: list[str] = []
        for package in imports:
            # GigaAM imports pyannote only inside its separate diarization helper;
            # basic local transcribe() does not execute that function.
            if package == "pyannote":
                continue
            try:
                importlib.import_module(package)
            except ImportError as error:
                if "No module named" not in str(error):
                    raise
                missing.append(package)
        if missing:
            raise ImportError(
                "GigaAM model code requires missing runtime packages: " + ", ".join(missing)
            )
        return imports

    module_utils.check_imports = check_imports_without_optional_diarization
    try:
        config = AutoConfig.from_pretrained(
            str(model_dir),
            trust_remote_code=True,
            local_files_only=True,
        )
        recognizer = AutoModel.from_config(config, trust_remote_code=True)
        state_dict = torch.load(
            model_dir / "pytorch_model.bin",
            map_location="cpu",
            weights_only=True,
        )
        recognizer.load_state_dict(state_dict, strict=True)
    finally:
        module_utils.check_imports = original_check_imports
    recognizer.to("cpu")
    recognizer.eval()
    load_ms = (time.perf_counter() - started) * 1000
    if next(recognizer.parameters()).device.type != "cpu":
        raise RuntimeError("GigaAM did not load on CPU")

    started = time.perf_counter()
    with torch.inference_mode():
        transcript = str(recognizer.transcribe(str(audio_path))).strip()
    inference_ms = (time.perf_counter() - started) * 1000
    if not transcript or not any("\u0400" <= char <= "\u04ff" for char in transcript):
        raise RuntimeError(f"GigaAM did not return a Russian transcript: {transcript!r}")

    return {
        "status": "passed",
        "revision": model["revision"],
        "variant": model["variant"],
        "device": "cpu",
        "dtype": str(next(recognizer.parameters()).dtype),
        "threads": threads,
        "model_load_ms": round(load_ms, 3),
        "inference_ms": round(inference_ms, 3),
        "audio_fixture": str(audio_path.relative_to(ROOT)),
        "transcript_ru": transcript,
        "verified_files": verified,
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        choices=["all", "embeddinggemma2", "qwen3_0_6b", "gigaam_v3_e2e_ctc"],
        default="all",
    )
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="set Hugging Face offline flags; model files are always loaded from local paths",
    )
    args = parser.parse_args()
    if args.threads < 1 or args.max_tokens < 1:
        parser.error("--threads and --max-tokens must be positive")
    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    models_dir = args.models_dir.resolve()
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    selected = (
        ["embeddinggemma2", "qwen3_0_6b", "gigaam_v3_e2e_ctc"]
        if args.model == "all"
        else [args.model]
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "runtime_target": "cpu",
        "offline_requested": args.offline,
        "python": sys.version.split()[0],
        "os": platform.platform(),
        "cpu": platform.processor(),
        "models": {},
    }
    for name in selected:
        if name == "embeddinggemma2":
            report["models"][name] = _embedding_smoke(
                lock["models"][name], models_dir, threads=args.threads
            )
        elif name == "qwen3_0_6b":
            report["models"][name] = _qwen_smoke(
                lock["models"][name],
                models_dir,
                threads=args.threads,
                max_tokens=args.max_tokens,
            )
        else:
            report["models"][name] = _gigaam_smoke(
                lock["models"][name], models_dir, threads=args.threads
            )
        print(f"{name}: passed", flush=True)

    _write_report(args.report.resolve(), report)
    print(f"Smoke results saved to {args.report.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MissingModelFiles as error:
        print(f"model unavailable: {error}", file=sys.stderr)
        raise SystemExit(2) from error
