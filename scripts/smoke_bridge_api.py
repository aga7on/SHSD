from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import time
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "models.lock.json"
MODEL_CARD = "https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2"
MULTIMODAL_GUIDE = "https://ai.google.dev/gemma/docs/embeddinggemma/multimodal-embeddinggemma-with-sentence-transformers"
QWEN_CARD = "https://huggingface.co/Qwen/Qwen3-0.6B"


def _sample_video(
    path: Path, *, start_ms: int, end_ms: int, max_frames: int
) -> tuple[list[Any], list[int], dict[str, Any]]:
    import av
    from PIL import Image

    if max_frames < 1 or start_ms < 0 or end_ms <= start_ms:
        raise ValueError("invalid video interval or frame limit")
    frames: list[Any] = []
    pts_list: list[int] = []
    with av.open(str(path), mode="r") as container:
        if not container.streams.video:
            raise ValueError(f"video has no video stream: {path}")
        stream = container.streams.video[0]
        source_fps = float(stream.average_rate) if stream.average_rate else 1.0
        if not math.isfinite(source_fps) or source_fps <= 0:
            source_fps = 1.0
        source_frame_count = int(stream.frames) if stream.frames else 0
        duration_ms = (
            round(container.duration * 1000 / av.time_base)
            if container.duration is not None
            else round(float(stream.duration * stream.time_base) * 1000)
            if stream.duration is not None and stream.time_base is not None
            else end_ms
        )
        clip_end_ms = min(duration_ms, end_ms)
        if clip_end_ms <= start_ms:
            raise ValueError("requested video interval is outside the source")
        span_ms = clip_end_ms - start_ms
        n_targets = min(max_frames, max(1, math.ceil(span_ms / 1000)))
        targets = [start_ms + round(i * span_ms / n_targets) for i in range(n_targets)]
        target_i = 0
        fallback_ms = start_ms
        for frame in container.decode(video=0):
            pts_ms = fallback_ms
            if frame.pts is not None and frame.time_base is not None:
                tb = Fraction(int(frame.time_base.numerator), int(frame.time_base.denominator))
                pts_ms = round(int(frame.pts) * tb * 1000)
            fallback_ms = max(pts_ms + 1, fallback_ms + 1)
            if pts_ms < start_ms or target_i >= len(targets):
                continue
            if pts_ms < targets[target_i]:
                continue
            image = Image.fromarray(frame.to_ndarray(format="rgb24"))
            while target_i < len(targets) and pts_ms >= targets[target_i]:
                frames.append(image)
                pts_list.append(pts_ms)
                target_i += 1
            if len(frames) >= max_frames:
                break
    if not frames:
        raise ValueError("no frames sampled")
    total_num_frames = (
        source_frame_count
        if source_frame_count > 0
        else max(1, round(duration_ms * source_fps / 1000))
    )
    metadata = {
        "total_num_frames": total_num_frames,
        "fps": source_fps,
        "duration": duration_ms / 1000,
        "frames_indices": [round(pts_ms * source_fps / 1000) for pts_ms in pts_list],
    }
    return frames, pts_list, metadata


def _read_audio(path: Path, *, target_samples: int) -> tuple[Any, int]:
    import av
    import numpy as np

    with av.open(str(path), mode="r") as container:
        if not container.streams.audio:
            raise ValueError(f"audio has no audio stream: {path}")
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=16_000)
        parts: list[Any] = []
        count = 0
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                part = np.asarray(converted.to_ndarray(), dtype=np.float32).reshape(-1)
                parts.append(part)
                count += part.size
                if count >= target_samples:
                    break
            if count >= target_samples:
                break
        audio = np.concatenate(parts)[:target_samples]
    return audio, 16_000


def _tensor_summary(value: Any, *, include_values: bool = False) -> dict[str, Any] | None:
    import torch

    if not torch.is_tensor(value):
        return None
    result: dict[str, Any] = {
        "shape": list(value.shape),
        "dtype": str(value.dtype),
        "finite": bool(torch.isfinite(value).all().item()) if value.is_floating_point() else True,
    }
    if include_values and value.numel():
        flat = value.detach().reshape(-1)
        result["first_values"] = flat[:12].to(device="cpu").tolist()
    return result


def _embedding_probe(threads: int) -> dict[str, Any]:
    import numpy as np
    import sentence_transformers
    import torch
    import transformers
    from PIL import Image
    from sentence_transformers import SentenceTransformer

    from shsd.models.artifacts import verify_local_artifacts

    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    model_info = lock["models"]["embeddinggemma2"]
    verified = verify_local_artifacts("embeddinggemma2", model_info, ROOT / "models")
    torch.set_num_threads(threads)
    encoder = SentenceTransformer(
        str(ROOT / "models" / "embeddinggemma2"),
        device="cpu",
        local_files_only=True,
    )
    if str(encoder.device) != "cpu":
        raise RuntimeError(f"expected CPU encoder, got {encoder.device}")

    captured: dict[str, Any] = {}

    def capture_transformer_output(_module: Any, _args: Any, output: Any) -> None:
        if not hasattr(output, "keys"):
            captured["output_type"] = str(type(output))
            return
        captured["keys"] = sorted(output.keys())
        for key in (
            "token_embeddings",
            "attention_mask",
            "image_position_ids",
            "video_position_ids",
            "num_frames_per_video",
            "modality",
        ):
            value = output.get(key)
            summary = _tensor_summary(
                value,
                include_values=key
                in {"image_position_ids", "video_position_ids", "num_frames_per_video", "modality"},
            )
            if summary is not None:
                captured[key] = summary
        input_ids = output.get("input_ids")
        if torch.is_tensor(input_ids) and input_ids.ndim == 2 and input_ids.shape[0] == 1:
            captured["input_ids"] = input_ids[0].detach().to(device="cpu").tolist()

    hook = encoder[0].register_forward_hook(capture_transformer_output)
    audio_path = ROOT / "tests" / "fixtures" / "media" / "audio_speech_ru.wav"
    video_path = ROOT / "tests" / "fixtures" / "media" / "video_scene_cuts_8s.mp4"
    audio, sample_rate = _read_audio(audio_path, target_samples=80_000)
    frames, pts_ms, video_metadata = _sample_video(
        video_path, start_ms=0, end_ms=5_000, max_frames=4
    )
    inputs = {
        "IMAGE": {"image": Image.new("RGB", (96, 64), (40, 80, 120))},
        "AUDIO": {"audio": {"array": audio, "sampling_rate": sample_rate}},
        "VIDEO": {"video": {"array": frames, "video_metadata": video_metadata}},
        "AV": {
            "audio": {"array": audio, "sampling_rate": sample_rate},
            "video": {"array": frames, "video_metadata": video_metadata},
        },
    }
    modes: dict[str, Any] = {}
    try:
        for mode, item in inputs.items():
            captured.clear()
            started = time.perf_counter()
            pooled = encoder.encode(
                item,
                batch_size=1,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=False,
                processing_kwargs=(
                    {"video": {"do_sample_frames": False, "add_timestamps": True}}
                    if mode in {"VIDEO", "AV"}
                    else None
                ),
            )
            vector = np.asarray(pooled)
            token_info = captured.get("token_embeddings")
            if token_info is None:
                raise RuntimeError(f"{mode} did not expose token_embeddings before pooling")
            decoded_tokens = (
                encoder[0].tokenizer.decode(
                    captured["input_ids"], clean_up_tokenization_spaces=False
                )
                if isinstance(captured.get("input_ids"), list)
                else ""
            )
            modes[mode] = {
                "status": "passed",
                "pooled_shape": list(vector.shape),
                "pooled_finite": bool(np.isfinite(vector).all()),
                "token_embeddings": token_info,
                "attention_mask": captured.get("attention_mask"),
                "position_or_frame_metadata": {
                    key: captured[key]
                    for key in (
                        "image_position_ids",
                        "video_position_ids",
                        "num_frames_per_video",
                        "modality",
                    )
                    if key in captured
                },
                "input_token_keys": captured.get("keys", []),
                "decoded_input_prefix": decoded_tokens[:180],
                "video_timestamp_markers": re.findall(r"\b\d{2}:\d{2}\b", decoded_tokens),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
    finally:
        hook.remove()

    return {
        "status": "passed",
        "model_repo": model_info["repo_id"],
        "model_revision": model_info["revision"],
        "verified_files": verified,
        "device": str(encoder.device),
        "dtype": str(encoder.dtype),
        "torch": torch.__version__,
        "sentence_transformers": sentence_transformers.__version__,
        "transformers": transformers.__version__,
        "threads": threads,
        "video_fixture": str(video_path.relative_to(ROOT)),
        "sampled_video_pts_ms": pts_ms,
        "video_metadata": video_metadata,
        "audio_fixture": str(audio_path.relative_to(ROOT)),
        "audio_samples": int(audio.size),
        "audio_seconds": round(audio.size / sample_rate, 4),
        "modes": modes,
    }


def _qwen_api_probe() -> dict[str, Any]:
    import torch
    import transformers
    from transformers import Qwen3Config
    from transformers.models.qwen3.modeling_qwen3 import Qwen3ForCausalLM

    torch.manual_seed(0)
    config = Qwen3Config(
        vocab_size=64,
        hidden_size=32,
        intermediate_size=64,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        head_dim=8,
        max_position_embeddings=32,
        use_cache=False,
    )
    model = Qwen3ForCausalLM(config).cpu().eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    params_before = [parameter.detach().clone() for parameter in model.parameters()]
    token_ids = torch.tensor([[1, 2]], dtype=torch.long)
    prompt = model.get_input_embeddings()(token_ids)
    prefix = torch.randn(1, 4, config.hidden_size, requires_grad=True)
    inputs_embeds = torch.cat((prefix, prompt), dim=1)
    attention_mask = torch.ones(inputs_embeds.shape[:2], dtype=torch.long)
    output = model(
        inputs_embeds=inputs_embeds,
        attention_mask=attention_mask,
        use_cache=False,
    )
    loss = output.logits.float().square().mean()
    loss.backward()
    generated = model.generate(
        inputs_embeds=inputs_embeds.detach(),
        attention_mask=attention_mask,
        max_new_tokens=2,
        do_sample=False,
    )
    unchanged = all(
        torch.equal(before, after.detach())
        for before, after in zip(params_before, model.parameters(), strict=True)
    )
    return {
        "status": "passed" if prefix.grad is not None and unchanged else "failed",
        "transformers": transformers.__version__,
        "class": "Qwen3ForCausalLM",
        "checkpoint_loaded": False,
        "synthetic_config": {
            "vocab_size": config.vocab_size,
            "hidden_size": config.hidden_size,
            "layers": config.num_hidden_layers,
            "attention_heads": config.num_attention_heads,
            "kv_heads": config.num_key_value_heads,
            "head_dim": config.head_dim,
        },
        "soft_prefix_api": (
            "inputs_embeds accepted by actual forward and generate calls on a synthetic "
            "Qwen3ForCausalLM instance"
        ),
        "forward_logits_shape": list(output.logits.shape),
        "loss_finite": bool(torch.isfinite(loss).item()),
        "prefix_gradient_finite": bool(
            prefix.grad is not None and torch.isfinite(prefix.grad).all().item()
        ),
        "generate_status": "passed",
        "generated_shape": list(generated.shape),
        "frozen_parameter_tensors_unchanged": unchanged,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline F10.01 API smoke tests; no training or network access."
    )
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "benchmarks" / "reports" / "bridge_f10" / "api_smoke.json",
    )
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    report = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "task": "F10.01",
        "network_disabled": True,
        "host": {"os": platform.platform(), "cpu": platform.processor()},
        "embeddinggemma": _embedding_probe(args.threads),
        "qwen_transformers_synthetic": _qwen_api_probe(),
        "scope": (
            "Synthetic Qwen API smoke is not a checkpoint quality/performance result. "
            "The pinned GGUF CPU custom-prefix path is checked separately by "
            "scripts/smoke_llama_cpp_prefix.py."
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    serialized_report = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.report.write_text(serialized_report, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
