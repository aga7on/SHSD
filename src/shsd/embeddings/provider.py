"""Local CPU-only EmbeddingGemma 2 inference."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np
from numpy.typing import ArrayLike

from shsd.embeddings.cache import EMBEDDING_DIM, DiskEmbeddingCache, normalize_embedding
from shsd.ingest.clock import pts_to_ms
from shsd.models.artifacts import verify_local_artifacts

if TYPE_CHECKING:
    from shsd.workers.embedding_worker import SharedEmbeddingDispatcher

PREPROCESS_VERSION = "embeddinggemma2-st-v4-audio-video-metadata"
VIDEO_PREPROCESS_VERSION = "embeddinggemma2-st-v5-video-source-pts"
JOINT_PREPROCESS_VERSION = "embeddinggemma2-st-v5-av-source-pts"
SAMPLE_RATE = 16_000
DEFAULT_IMAGE_SOFT_TOKENS = 280
COMPACT_IMAGE_SOFT_TOKENS = 140


class _FairSemaphore:
    """FIFO permit gate for bounded calls into the shared model instance."""

    def __init__(self, capacity: int = 1) -> None:
        if capacity < 1:
            raise ValueError("inference capacity must be positive")
        self._capacity = capacity
        self._condition = threading.Condition()
        self._next_ticket = 0
        self._serving_ticket = 0
        self._active = 0
        self._cancelled_tickets: set[int] = set()

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        with self._condition:
            if not blocking:
                if self._next_ticket != self._serving_ticket or self._active >= self._capacity:
                    return False
                self._next_ticket += 1
                self._serving_ticket += 1
                self._active += 1
                self._advance_cancelled()
                return True

            ticket = self._next_ticket
            self._next_ticket += 1
            if timeout < 0:
                self._condition.wait_for(
                    lambda: ticket == self._serving_ticket and self._active < self._capacity
                )
                self._active += 1
                self._serving_ticket += 1
                self._advance_cancelled()
                self._condition.notify_all()
                return True
            if self._condition.wait_for(
                lambda: ticket == self._serving_ticket and self._active < self._capacity,
                timeout=timeout,
            ):
                self._active += 1
                self._serving_ticket += 1
                self._advance_cancelled()
                self._condition.notify_all()
                return True
            self._cancelled_tickets.add(ticket)
            self._advance_cancelled()
            self._condition.notify_all()
            return False

    def release(self) -> None:
        with self._condition:
            if self._active == 0:
                raise RuntimeError("cannot release an unlocked fair lock")
            self._active -= 1
            self._advance_cancelled()
            self._condition.notify_all()

    def _advance_cancelled(self) -> None:
        while self._serving_ticket in self._cancelled_tickets:
            self._cancelled_tickets.remove(self._serving_ticket)
            self._serving_ticket += 1

    @property
    def waiting_count(self) -> int:
        with self._condition:
            return max(
                0,
                self._next_ticket - self._serving_ticket - len(self._cancelled_tickets),
            )

    def __enter__(self) -> _FairSemaphore:
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


# Kept for internal callers and tests that still refer to the original capacity-one gate.
_FairLock = _FairSemaphore


def _load_video_sample(
    video_path: Path,
    *,
    interval_ms: tuple[int, int] | None = None,
    max_frames: int = 32,
) -> tuple[list[Any], tuple[int, ...], dict[str, Any]]:
    """Decode sampled frames while retaining original source PTS and model metadata."""
    if max_frames < 1:
        raise ValueError("max_frames must be positive")
    if interval_ms is not None and (interval_ms[0] < 0 or interval_ms[1] <= interval_ms[0]):
        raise ValueError("interval must satisfy 0 <= start_ms < end_ms")
    import av
    from PIL import Image

    frames: list[Any] = []
    frame_pts_ms: list[int] = []
    with av.open(str(video_path), mode="r") as container:
        if not container.streams.video:
            raise ValueError(f"video input has no video stream: {video_path}")
        stream = container.streams.video[0]
        duration_ms = (
            round(container.duration * 1000 / av.time_base)
            if container.duration is not None
            else round(float(stream.duration * stream.time_base) * 1000)
            if stream.duration is not None and stream.time_base is not None
            else None
        )
        source_fps = float(stream.average_rate) if stream.average_rate else 1.0
        if not np.isfinite(source_fps) or source_fps <= 0:
            source_fps = 1.0
        source_frame_count = int(stream.frames) if stream.frames else 0
        clip_start_ms = interval_ms[0] if interval_ms is not None else 0
        clip_end_ms = (
            min(duration_ms, interval_ms[1])
            if duration_ms is not None and interval_ms is not None
            else duration_ms
            if interval_ms is None
            else interval_ms[1]
        )
        if clip_end_ms is not None and clip_end_ms <= clip_start_ms:
            raise ValueError("video interval does not overlap the source duration")
        if duration_ms is not None and duration_ms > 0:
            assert clip_end_ms is not None
            clip_duration_ms = clip_end_ms - clip_start_ms
            frame_count = min(max_frames, max(1, (clip_duration_ms + 999) // 1000))
            target_times = [
                clip_start_ms + round(index * clip_duration_ms / frame_count)
                for index in range(frame_count)
            ]
        else:
            target_times = list(range(clip_start_ms, clip_start_ms + max_frames * 1000, 1000))

        target_index = 0
        fallback_ms = 0
        for frame in container.decode(video=0):
            timestamp_ms = fallback_ms
            if frame.pts is not None and frame.time_base is not None:
                time_base = Fraction(
                    int(frame.time_base.numerator), int(frame.time_base.denominator)
                )
                timestamp_ms = pts_to_ms(int(frame.pts), time_base)
            fallback_ms = max(timestamp_ms + 1, fallback_ms + 1)
            if target_index >= len(target_times):
                break
            if timestamp_ms < target_times[target_index]:
                continue
            image = Image.fromarray(frame.to_ndarray(format="rgb24"))
            while target_index < len(target_times) and timestamp_ms >= target_times[target_index]:
                frames.append(image)
                frame_pts_ms.append(timestamp_ms)
                target_index += 1
            if len(frames) >= max_frames:
                break
    if not frames:
        raise ValueError(f"video input did not decode any frames: {video_path}")
    resolved_duration_ms = duration_ms or max(frame_pts_ms) + 1
    total_num_frames = source_frame_count or max(1, round(resolved_duration_ms * source_fps / 1000))
    video_metadata = {
        "total_num_frames": total_num_frames,
        "fps": source_fps,
        "duration": resolved_duration_ms / 1000,
        "frames_indices": [max(0, round(pts_ms * source_fps / 1000)) for pts_ms in frame_pts_ms],
    }
    return frames, tuple(frame_pts_ms), video_metadata


def _load_video_frames(
    video_path: Path,
    *,
    interval_ms: tuple[int, int] | None = None,
    max_frames: int = 32,
) -> list[Any]:
    """Compatibility wrapper for callers that only need sampled frame pixels."""
    frames, _frame_pts_ms, _video_metadata = _load_video_sample(
        video_path,
        interval_ms=interval_ms,
        max_frames=max_frames,
    )
    return frames


def _video_input(frames: list[Any], video_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mark sampled frames so the model does not sample them twice."""
    return {
        "video": {"array": frames, "video_metadata": video_metadata},
    }


@dataclass(frozen=True, slots=True)
class EmbeddingRecord:
    embedding: np.ndarray
    model_revision: str
    input_preprocess_version: str
    modality: str
    embedding_dim: int
    norm: float
    created_at: str
    latency_ms: float
    window_id: str
    interval_ms: tuple[int, int] | None
    cache_hit: bool

    def to_dict(self, *, include_embedding: bool = False) -> dict[str, Any]:
        result = asdict(self)
        if not include_embedding:
            result.pop("embedding")
        else:
            result["embedding"] = self.embedding.tolist()
        if self.interval_ms is not None:
            result["interval_ms"] = list(self.interval_ms)
        return result


@dataclass(frozen=True, slots=True)
class SequenceFeatureRecord:
    """Unpooled encoder tokens plus masks and source-time metadata for bridge R&D."""

    token_embeddings: np.ndarray
    attention_mask: np.ndarray
    input_token_ids: np.ndarray | None
    encoder_metadata: dict[str, np.ndarray]
    model_revision: str
    input_preprocess_version: str
    modality: str
    interval_ms: tuple[int, int] | None
    frame_pts_ms: tuple[int, ...]
    video_metadata: dict[str, Any] | None
    latency_ms: float

    def to_dict(self, *, include_features: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "model_revision": self.model_revision,
            "input_preprocess_version": self.input_preprocess_version,
            "modality": self.modality,
            "interval_ms": list(self.interval_ms) if self.interval_ms else None,
            "frame_pts_ms": list(self.frame_pts_ms),
            "video_metadata": self.video_metadata,
            "latency_ms": self.latency_ms,
            "token_embeddings_shape": list(self.token_embeddings.shape),
            "attention_mask_shape": list(self.attention_mask.shape),
            "input_token_ids_shape": (
                list(self.input_token_ids.shape) if self.input_token_ids is not None else None
            ),
            "encoder_metadata_shapes": {
                name: list(value.shape) for name, value in self.encoder_metadata.items()
            },
        }
        if include_features:
            result.update(
                {
                    "token_embeddings": self.token_embeddings.tolist(),
                    "attention_mask": self.attention_mask.tolist(),
                    "input_token_ids": (
                        self.input_token_ids.tolist() if self.input_token_ids is not None else None
                    ),
                    "encoder_metadata": {
                        name: value.tolist() for name, value in self.encoder_metadata.items()
                    },
                }
            )
        return result


class EmbeddingProvider:
    """Load the pinned model once and expose cached audio, frame, and text encoders."""

    def __init__(
        self,
        model: dict[str, Any],
        models_dir: Path,
        *,
        cache_dir: Path | None = None,
        threads: int = 4,
        inference_concurrency: int = 1,
        enabled_modalities: set[str] | None = None,
    ) -> None:
        if threads < 1:
            raise ValueError("threads must be positive")
        if inference_concurrency < 1:
            raise ValueError("inference_concurrency must be positive")
        if enabled_modalities is not None and not enabled_modalities.issubset(
            {"audio", "image", "video"}
        ):
            raise ValueError("enabled_modalities may contain audio, image, and video")
        self.enabled_modalities = None if enabled_modalities is None else set(enabled_modalities)
        self.model = model
        self.inference_concurrency = inference_concurrency
        self.model_dir = models_dir / "embeddinggemma2"
        verify_local_artifacts("embeddinggemma2", model, models_dir)

        import torch
        from sentence_transformers import SentenceTransformer
        from threadpoolctl import threadpool_limits

        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        torch.set_num_threads(threads)
        self._native_thread_limit = threadpool_limits(limits=threads)
        self.threads = threads
        config_kwargs: dict[str, Any] = {}
        if enabled_modalities is not None:
            if "audio" not in enabled_modalities:
                config_kwargs["audio_config"] = None
            if not enabled_modalities.intersection({"image", "video"}):
                config_kwargs["vision_config"] = None
        self.encoder = SentenceTransformer(
            str(self.model_dir),
            device="cpu",
            local_files_only=True,
            config_kwargs=config_kwargs,
        )
        if str(self.encoder.device) != "cpu":
            raise RuntimeError(f"EmbeddingGemma did not load on CPU: {self.encoder.device}")
        self.cache = DiskEmbeddingCache(cache_dir or models_dir / "cache" / "embeddinggemma2")
        self._inference_lock = _FairSemaphore(inference_concurrency)
        self._revision = str(model["revision"])
        self._torch = torch

    def set_num_threads(self, threads: int) -> None:
        """Set the current process's CPU inference thread limit."""
        if threads < 1:
            raise ValueError("threads must be positive")
        self._torch.set_num_threads(threads)
        self.threads = threads

    def _cache_key(
        self,
        modality: str,
        content: bytes,
        *,
        preprocess_version: str = PREPROCESS_VERSION,
    ) -> str:
        return self.cache.key(
            model_revision=self._revision,
            preprocess_version=preprocess_version,
            modality=modality,
            content=content,
        )

    def _record(
        self,
        vector: np.ndarray,
        *,
        modality: str,
        interval_ms: tuple[int, int] | None,
        latency_ms: float,
        cache_hit: bool,
        identity: bytes,
        window_identity: bytes | None = None,
        input_preprocess_version: str = PREPROCESS_VERSION,
    ) -> EmbeddingRecord:
        normalized = normalize_embedding(
            np.asarray(vector, dtype=np.float32).reshape(EMBEDDING_DIM)
        )
        identity_hash = hashlib.sha256(window_identity or identity).hexdigest()[:20]
        window_id = f"{modality}:{self._revision[:12]}:{identity_hash}"
        return EmbeddingRecord(
            embedding=normalized,
            model_revision=self._revision,
            input_preprocess_version=input_preprocess_version,
            modality=modality,
            embedding_dim=EMBEDDING_DIM,
            norm=float(np.linalg.norm(normalized)),
            created_at=datetime.now(UTC).isoformat(),
            latency_ms=round(latency_ms, 3),
            window_id=window_id,
            interval_ms=interval_ms,
            cache_hit=cache_hit,
        )

    def _encode_missing(
        self,
        inputs: Any,
        count: int,
        *,
        processing_kwargs: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, float]:
        with self._inference_lock, self._torch.inference_mode():
            # Exclude time waiting behind another stream's shared-model call.
            started = time.perf_counter()
            encode = cast(Any, self.encoder).encode
            kwargs = {} if processing_kwargs is None else {"processing_kwargs": processing_kwargs}
            vectors = encode(
                inputs,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
                **kwargs,
            )
            latency_ms = (time.perf_counter() - started) * 1000
        array = np.asarray(vectors, dtype=np.float32)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        if array.shape != (count, EMBEDDING_DIM) or not np.isfinite(array).all():
            raise RuntimeError(
                f"EmbeddingGemma returned invalid vectors: expected ({count}, {EMBEDDING_DIM}), "
                f"received {array.shape}"
            )
        return array, latency_ms

    def _encode_sequence(
        self,
        inputs: Any,
        *,
        modality: str,
        interval_ms: tuple[int, int] | None,
        frame_pts_ms: tuple[int, ...] = (),
        video_metadata: dict[str, Any] | None = None,
        processing_kwargs: dict[str, Any] | None = None,
        input_preprocess_version: str = PREPROCESS_VERSION,
    ) -> SequenceFeatureRecord:
        """Return encoder tokens before pooling without changing the cached API."""
        captured: dict[str, Any] = {}
        metadata_names = (
            "image_position_ids",
            "video_position_ids",
            "num_frames_per_video",
            "modality",
            "input_features_mask",
        )

        def capture_transformer_output(_module: Any, _args: Any, output: Any) -> None:
            if not hasattr(output, "get"):
                return
            for name in ("token_embeddings", "attention_mask", "input_ids", *metadata_names):
                value = output.get(name)
                if self._torch.is_tensor(value):
                    captured[name] = value.detach().to(device="cpu")

        transformer = self.encoder[0]
        hook = transformer.register_forward_hook(capture_transformer_output)
        try:
            with self._inference_lock, self._torch.inference_mode():
                started = time.perf_counter()
                encode = cast(Any, self.encoder).encode
                kwargs = (
                    {} if processing_kwargs is None else {"processing_kwargs": processing_kwargs}
                )
                encode(
                    inputs,
                    batch_size=1,
                    convert_to_numpy=True,
                    normalize_embeddings=False,
                    show_progress_bar=False,
                    **kwargs,
                )
                latency_ms = (time.perf_counter() - started) * 1000
        finally:
            hook.remove()

        tokens = captured.get("token_embeddings")
        if tokens is None or tokens.ndim != 3 or tokens.shape[0] != 1:
            raise RuntimeError("EmbeddingGemma did not expose one unpooled token sequence")
        token_array = np.asarray(tokens[0].float().numpy(), dtype=np.float32)
        if token_array.shape[1] != EMBEDDING_DIM or not np.isfinite(token_array).all():
            raise RuntimeError(
                f"EmbeddingGemma returned invalid token features: {token_array.shape}"
            )
        attention = captured.get("attention_mask")
        if attention is None:
            attention_array = np.ones(token_array.shape[0], dtype=np.bool_)
        else:
            if attention.ndim != 2 or attention.shape[0] != 1:
                raise RuntimeError("EmbeddingGemma returned an invalid token attention mask")
            attention_array = np.asarray(attention[0].numpy(), dtype=np.bool_)
        if attention_array.shape != (token_array.shape[0],):
            raise RuntimeError("token sequence and attention mask lengths differ")
        token_ids = captured.get("input_ids")
        token_id_array = None
        if token_ids is not None:
            if token_ids.ndim != 2 or token_ids.shape[0] != 1:
                raise RuntimeError("EmbeddingGemma returned invalid input token IDs")
            token_id_array = np.asarray(token_ids[0].numpy(), dtype=np.int64)
            if token_id_array.shape != attention_array.shape:
                raise RuntimeError("input token IDs and attention mask lengths differ")
            token_id_array.setflags(write=False)
        metadata_arrays = {
            name: np.asarray(
                value.float().numpy() if value.is_floating_point() else value.numpy()
            ).copy()
            for name in metadata_names
            if (value := captured.get(name)) is not None
        }
        for value in (token_array, attention_array, *metadata_arrays.values()):
            value.setflags(write=False)
        return SequenceFeatureRecord(
            token_embeddings=token_array,
            attention_mask=attention_array,
            input_token_ids=token_id_array,
            encoder_metadata=metadata_arrays,
            model_revision=self._revision,
            input_preprocess_version=input_preprocess_version,
            modality=modality,
            interval_ms=interval_ms,
            frame_pts_ms=frame_pts_ms,
            video_metadata=dict(video_metadata) if video_metadata is not None else None,
            latency_ms=round(latency_ms, 3),
        )

    @staticmethod
    def _audio_array(samples: ArrayLike) -> tuple[np.ndarray, bytes]:
        audio = np.asarray(samples)
        if audio.ndim != 1 or audio.size == 0:
            raise ValueError("audio input must be a non-empty mono PCM vector")
        if np.issubdtype(audio.dtype, np.integer):
            scale = float(max(abs(np.iinfo(audio.dtype).min), np.iinfo(audio.dtype).max))
            audio = audio.astype(np.float32) / scale
        else:
            audio = audio.astype(np.float32, copy=False)
        audio = np.nan_to_num(audio, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        normalized = np.ascontiguousarray(np.clip(audio, -1.0, 1.0), dtype="<f4")
        identity = b"pcm-f32-16000-mono\0" + normalized.tobytes()
        return normalized, identity

    def encode_audio(
        self, pcm_16k_mono: ArrayLike, interval_ms: tuple[int, int]
    ) -> EmbeddingRecord:
        """Encode one mono 16 kHz waveform and associate it with source time."""
        if self._modalities_disabled("audio"):
            raise RuntimeError("audio encoder was disabled when EmbeddingGemma was loaded")
        start_ms, end_ms = interval_ms
        if start_ms < 0 or end_ms <= start_ms:
            raise ValueError("interval must satisfy 0 <= start_ms < end_ms")
        audio, identity = self._audio_array(pcm_16k_mono)
        expected_samples = round((end_ms - start_ms) * SAMPLE_RATE / 1000)
        if abs(audio.size - expected_samples) > SAMPLE_RATE // 10:
            raise ValueError("audio sample count does not match the supplied interval")
        window_identity = f"{start_ms}:{end_ms}\0".encode("ascii") + identity
        key = self._cache_key("audio", identity)
        cached = self.cache.get(key)
        if cached is not None:
            return self._record(
                cached,
                modality="audio",
                interval_ms=interval_ms,
                latency_ms=0.0,
                cache_hit=True,
                identity=identity,
                window_identity=window_identity,
            )

        encoded, latency_ms = self._encode_missing(
            {"audio": {"array": audio, "sampling_rate": SAMPLE_RATE}}, 1
        )
        vector = encoded[0]
        self.cache.put(key, vector)
        return self._record(
            vector,
            modality="audio",
            interval_ms=interval_ms,
            latency_ms=latency_ms,
            cache_hit=False,
            identity=identity,
            window_identity=window_identity,
        )

    @staticmethod
    def _rgb_image(image_rgb: ArrayLike) -> tuple[np.ndarray, bytes]:
        image = np.asarray(image_rgb)
        if image.ndim != 3 or image.shape[2] not in (3, 4):
            raise ValueError("frame must be an RGB/RGBA image array")
        rgb = image[..., :3]
        if np.issubdtype(rgb.dtype, np.floating):
            maximum = float(np.nanmax(rgb))
            if maximum <= 1.0:
                rgb = np.clip(rgb, 0.0, 1.0) * 255.0
        rgb8 = np.nan_to_num(np.clip(rgb, 0, 255), copy=True).astype(np.uint8)
        return rgb8, rgb8.tobytes()

    def encode_frame(
        self,
        image_rgb: ArrayLike,
        pts_ms: int,
        *,
        max_soft_tokens: int = DEFAULT_IMAGE_SOFT_TOKENS,
    ) -> EmbeddingRecord:
        """Encode an RGB frame; point timestamps are represented by a 1 ms half-open bin."""
        if self._modalities_disabled("image"):
            raise RuntimeError("vision encoder was disabled when EmbeddingGemma was loaded")
        if pts_ms < 0:
            raise ValueError("pts_ms must be non-negative")
        if max_soft_tokens not in {70, 140, 280, 560, 1120}:
            raise ValueError("max_soft_tokens must be one of 70, 140, 280, 560, or 1120")
        from PIL import Image

        image, content = self._rgb_image(image_rgb)
        identity = f"{image.shape[1]}x{image.shape[0]}\0".encode() + content
        preprocess_version = PREPROCESS_VERSION
        processing_kwargs = None
        if max_soft_tokens != DEFAULT_IMAGE_SOFT_TOKENS:
            identity += f"\0vision-soft-tokens={max_soft_tokens}".encode("ascii")
            preprocess_version = f"{PREPROCESS_VERSION}-vision-soft-tokens-{max_soft_tokens}"
            processing_kwargs = {"image": {"max_soft_tokens": max_soft_tokens}}
        window_identity = f"{pts_ms}\0".encode("ascii") + identity
        key = self._cache_key("image", identity)
        cached = self.cache.get(key)
        interval = (pts_ms, pts_ms + 1)
        if cached is not None:
            return self._record(
                cached,
                modality="image",
                interval_ms=interval,
                latency_ms=0.0,
                cache_hit=True,
                identity=identity,
                window_identity=window_identity,
                input_preprocess_version=preprocess_version,
            )
        encoded, latency_ms = self._encode_missing(
            {"image": Image.fromarray(image)},
            1,
            processing_kwargs=processing_kwargs,
        )
        vector = encoded[0]
        self.cache.put(key, vector)
        return self._record(
            vector,
            modality="image",
            interval_ms=interval,
            latency_ms=latency_ms,
            cache_hit=False,
            identity=identity,
            window_identity=window_identity,
            input_preprocess_version=preprocess_version,
        )

    def encode_video(
        self,
        video_path: Path,
        interval_ms: tuple[int, int] | None = None,
        *,
        force_recompute: bool = False,
    ) -> EmbeddingRecord:
        """Encode a local video with the model's native video input path."""
        if self._modalities_disabled("video"):
            raise RuntimeError("vision encoder was disabled when EmbeddingGemma was loaded")
        if not video_path.is_file():
            raise FileNotFoundError(video_path)
        if interval_ms is not None and (interval_ms[0] < 0 or interval_ms[1] <= interval_ms[0]):
            raise ValueError("interval must satisfy 0 <= start_ms < end_ms")
        digest = hashlib.sha256()
        with video_path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        file_identity = digest.digest()
        identity = (
            f"{interval_ms[0]}:{interval_ms[1]}\0".encode("ascii") + file_identity
            if interval_ms is not None
            else file_identity
        )
        window_identity = identity
        key = self._cache_key("video", identity, preprocess_version=VIDEO_PREPROCESS_VERSION)
        cached = None if force_recompute else self.cache.get(key)
        if cached is not None:
            return self._record(
                cached,
                modality="video",
                interval_ms=interval_ms,
                latency_ms=0.0,
                cache_hit=True,
                identity=identity,
                window_identity=window_identity,
                input_preprocess_version=VIDEO_PREPROCESS_VERSION,
            )
        frames, _frame_pts_ms, video_metadata = _load_video_sample(
            video_path,
            interval_ms=interval_ms,
        )
        encoded, latency_ms = self._encode_missing(
            _video_input(frames, video_metadata),
            1,
            processing_kwargs={"video": {"do_sample_frames": False, "add_timestamps": True}},
        )
        vector = encoded[0]
        self.cache.put(key, vector)
        return self._record(
            vector,
            modality="video",
            interval_ms=interval_ms,
            latency_ms=latency_ms,
            cache_hit=False,
            identity=identity,
            window_identity=window_identity,
            input_preprocess_version=VIDEO_PREPROCESS_VERSION,
        )

    def encode_joint(
        self,
        pcm_16k_mono: ArrayLike,
        video_path: Path,
        interval_ms: tuple[int, int],
        *,
        force_recompute: bool = False,
    ) -> EmbeddingRecord:
        """Encode one aligned audio waveform and video as one multimodal query."""
        if self._modalities_disabled("audio") or self._modalities_disabled("video"):
            raise RuntimeError("joint input requires enabled audio and vision encoders")
        if not video_path.is_file():
            raise FileNotFoundError(video_path)
        start_ms, end_ms = interval_ms
        if start_ms < 0 or end_ms <= start_ms:
            raise ValueError("interval must satisfy 0 <= start_ms < end_ms")
        audio, audio_identity = self._audio_array(pcm_16k_mono)
        expected_samples = round((end_ms - start_ms) * SAMPLE_RATE / 1000)
        if abs(audio.size - expected_samples) > SAMPLE_RATE // 10:
            raise ValueError("audio sample count does not match the supplied interval")
        video_digest = hashlib.sha256()
        with video_path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                video_digest.update(chunk)
        identity = (
            f"{start_ms}:{end_ms}\0".encode("ascii")
            + audio_identity
            + b"\0"
            + video_digest.digest()
        )
        window_identity = f"{start_ms}:{end_ms}\0".encode("ascii") + identity
        key = self._cache_key("joint", identity, preprocess_version=JOINT_PREPROCESS_VERSION)
        cached = None if force_recompute else self.cache.get(key)
        if cached is not None:
            return self._record(
                cached,
                modality="joint",
                interval_ms=interval_ms,
                latency_ms=0.0,
                cache_hit=True,
                identity=identity,
                window_identity=window_identity,
                input_preprocess_version=JOINT_PREPROCESS_VERSION,
            )
        frames, _frame_pts_ms, video_metadata = _load_video_sample(
            video_path,
            interval_ms=interval_ms,
        )
        encoded, latency_ms = self._encode_missing(
            {
                "audio": {"array": audio, "sampling_rate": SAMPLE_RATE},
                **_video_input(frames, video_metadata),
            },
            1,
            processing_kwargs={"video": {"do_sample_frames": False, "add_timestamps": True}},
        )
        vector = encoded[0]
        self.cache.put(key, vector)
        return self._record(
            vector,
            modality="joint",
            interval_ms=interval_ms,
            latency_ms=latency_ms,
            cache_hit=False,
            identity=identity,
            window_identity=window_identity,
            input_preprocess_version=JOINT_PREPROCESS_VERSION,
        )

    def encode_audio_features(
        self, pcm_16k_mono: ArrayLike, interval_ms: tuple[int, int]
    ) -> SequenceFeatureRecord:
        """Expose unpooled audio token features for an opt-in bridge caller."""
        if self._modalities_disabled("audio"):
            raise RuntimeError("audio encoder was disabled when EmbeddingGemma was loaded")
        start_ms, end_ms = interval_ms
        if start_ms < 0 or end_ms <= start_ms:
            raise ValueError("interval must satisfy 0 <= start_ms < end_ms")
        audio, _identity = self._audio_array(pcm_16k_mono)
        expected_samples = round((end_ms - start_ms) * SAMPLE_RATE / 1000)
        if abs(audio.size - expected_samples) > SAMPLE_RATE // 10:
            raise ValueError("audio sample count does not match the supplied interval")
        return self._encode_sequence(
            {"audio": {"array": audio, "sampling_rate": SAMPLE_RATE}},
            modality="audio",
            interval_ms=interval_ms,
        )

    def encode_frame_features(
        self,
        image_rgb: ArrayLike,
        pts_ms: int,
        *,
        max_soft_tokens: int = DEFAULT_IMAGE_SOFT_TOKENS,
    ) -> SequenceFeatureRecord:
        """Expose unpooled IMAGE tokens and the exact source frame timestamp."""
        if self._modalities_disabled("image"):
            raise RuntimeError("vision encoder was disabled when EmbeddingGemma was loaded")
        if pts_ms < 0:
            raise ValueError("pts_ms must be non-negative")
        if max_soft_tokens not in {70, 140, 280, 560, 1120}:
            raise ValueError("max_soft_tokens must be one of 70, 140, 280, 560, or 1120")
        from PIL import Image

        image, _identity = self._rgb_image(image_rgb)
        kwargs = (
            None
            if max_soft_tokens == DEFAULT_IMAGE_SOFT_TOKENS
            else {"image": {"max_soft_tokens": max_soft_tokens}}
        )
        preprocess_version = (
            PREPROCESS_VERSION
            if max_soft_tokens == DEFAULT_IMAGE_SOFT_TOKENS
            else f"{PREPROCESS_VERSION}-vision-soft-tokens-{max_soft_tokens}"
        )
        return self._encode_sequence(
            {"image": Image.fromarray(image)},
            modality="image",
            interval_ms=(pts_ms, pts_ms + 1),
            frame_pts_ms=(pts_ms,),
            processing_kwargs=kwargs,
            input_preprocess_version=preprocess_version,
        )

    def encode_video_features(
        self,
        video_path: Path,
        interval_ms: tuple[int, int] | None = None,
        *,
        max_frames: int = 32,
    ) -> SequenceFeatureRecord:
        """Expose VIDEO tokens with sampled source PTS and frame-index metadata."""
        if self._modalities_disabled("video"):
            raise RuntimeError("vision encoder was disabled when EmbeddingGemma was loaded")
        if not video_path.is_file():
            raise FileNotFoundError(video_path)
        frames, frame_pts_ms, video_metadata = _load_video_sample(
            video_path,
            interval_ms=interval_ms,
            max_frames=max_frames,
        )
        return self._encode_sequence(
            _video_input(frames, video_metadata),
            modality="video",
            interval_ms=interval_ms,
            frame_pts_ms=frame_pts_ms,
            video_metadata=video_metadata,
            processing_kwargs={"video": {"do_sample_frames": False, "add_timestamps": True}},
            input_preprocess_version=f"{VIDEO_PREPROCESS_VERSION}-max-frames-{max_frames}",
        )

    def encode_joint_features(
        self,
        pcm_16k_mono: ArrayLike,
        video_path: Path,
        interval_ms: tuple[int, int],
        *,
        max_frames: int = 32,
    ) -> SequenceFeatureRecord:
        """Expose AV tokens with aligned source interval and sampled video PTS."""
        if self._modalities_disabled("audio") or self._modalities_disabled("video"):
            raise RuntimeError("joint input requires enabled audio and vision encoders")
        if not video_path.is_file():
            raise FileNotFoundError(video_path)
        start_ms, end_ms = interval_ms
        if start_ms < 0 or end_ms <= start_ms:
            raise ValueError("interval must satisfy 0 <= start_ms < end_ms")
        audio, _identity = self._audio_array(pcm_16k_mono)
        expected_samples = round((end_ms - start_ms) * SAMPLE_RATE / 1000)
        if abs(audio.size - expected_samples) > SAMPLE_RATE // 10:
            raise ValueError("audio sample count does not match the supplied interval")
        frames, frame_pts_ms, video_metadata = _load_video_sample(
            video_path,
            interval_ms=interval_ms,
            max_frames=max_frames,
        )
        inputs = {
            "audio": {"array": audio, "sampling_rate": SAMPLE_RATE},
            **_video_input(frames, video_metadata),
        }
        return self._encode_sequence(
            inputs,
            modality="joint",
            interval_ms=interval_ms,
            frame_pts_ms=frame_pts_ms,
            video_metadata=video_metadata,
            processing_kwargs={"video": {"do_sample_frames": False, "add_timestamps": True}},
            input_preprocess_version=f"{JOINT_PREPROCESS_VERSION}-max-frames-{max_frames}",
        )

    def encode_texts(
        self, candidates: list[str], *, cache_namespace: str = ""
    ) -> list[EmbeddingRecord]:
        """Encode and cache candidate sentences so media chunks reuse their vectors."""
        if any(not candidate.strip() for candidate in candidates):
            raise ValueError("text candidates must be non-empty strings")
        if not candidates:
            return []
        if "\0" in cache_namespace:
            raise ValueError("cache_namespace must not contain a NUL character")

        keys: list[str] = []
        identities: list[bytes] = []
        cached_vectors: dict[int, np.ndarray] = {}
        missing_indices: list[int] = []
        inference_ms_per_vector = 0.0
        for index, candidate in enumerate(candidates):
            text_identity = candidate.encode("utf-8")
            identity = (
                cache_namespace.encode("utf-8") + b"\0" + text_identity
                if cache_namespace
                else text_identity
            )
            identities.append(identity)
            key = self._cache_key("text", identity)
            keys.append(key)
            vector = self.cache.get(key)
            if vector is None:
                missing_indices.append(index)
            else:
                cached_vectors[index] = vector

        if missing_indices:
            inputs = [candidates[index] for index in missing_indices]
            vectors, inference_ms = self._encode_missing(inputs, len(missing_indices))
            inference_ms_per_vector = inference_ms / len(missing_indices)
            for row, index in enumerate(missing_indices):
                cached_vectors[index] = vectors[row]
                self.cache.put(keys[index], vectors[row])

        return [
            self._record(
                cached_vectors[index],
                modality="text",
                interval_ms=None,
                latency_ms=0.0 if index not in missing_indices else inference_ms_per_vector,
                cache_hit=index not in missing_indices,
                identity=identities[index],
            )
            for index in range(len(candidates))
        ]

    def _modalities_disabled(self, modality: str) -> bool:
        """Return whether a requested non-text modality was omitted at model load."""
        enabled = getattr(self, "enabled_modalities", None)
        if enabled is None:
            return False
        if modality in {"image", "video"}:
            return not bool(enabled.intersection({"image", "video"}))
        return modality not in enabled


class EmbeddingProviderPool:
    """Reuse one CPU encoder per identical model, modality, and thread profile."""

    def __init__(self, *, inference_concurrency: int = 1) -> None:
        if inference_concurrency < 1:
            raise ValueError("inference_concurrency must be positive")
        self._lock = threading.RLock()
        self._providers: dict[
            tuple[str, str, str, int, int, tuple[str, ...] | None], EmbeddingProvider
        ] = {}
        self._dispatchers: dict[int, SharedEmbeddingDispatcher] = {}
        self.inference_concurrency = inference_concurrency

    def dispatcher_for(self, provider: EmbeddingProvider) -> SharedEmbeddingDispatcher:
        """Return the one bounded media-inference dispatcher for a pooled provider."""
        from shsd.workers.embedding_worker import SharedEmbeddingDispatcher

        provider_key = id(provider)
        with self._lock:
            dispatcher = self._dispatchers.get(provider_key)
            if dispatcher is None:
                dispatcher = SharedEmbeddingDispatcher(
                    queue_capacity=64,
                    worker_count=getattr(provider, "inference_concurrency", 1),
                )
                self._dispatchers[provider_key] = dispatcher
            return dispatcher

    def close_dispatchers(self, *, timeout: float | None = None) -> None:
        """Drain and stop shared workers when the owning API manager shuts down."""
        with self._lock:
            dispatchers = tuple(self._dispatchers.values())
            self._dispatchers.clear()
        for dispatcher in dispatchers:
            dispatcher.close(timeout=timeout)

    def get_or_create(
        self,
        model: dict[str, Any],
        models_dir: Path,
        *,
        cache_dir: Path | None = None,
        threads: int = 4,
        inference_concurrency: int | None = None,
        enabled_modalities: set[str] | None = None,
    ) -> EmbeddingProvider:
        """Build identical providers once, keeping concurrent first loads serialized."""
        resolved_models_dir = models_dir.resolve()
        resolved_cache_dir = (cache_dir or models_dir / "cache" / "embeddinggemma2").resolve()
        modality_key = None if enabled_modalities is None else tuple(sorted(enabled_modalities))
        concurrency = (
            self.inference_concurrency if inference_concurrency is None else inference_concurrency
        )
        if concurrency < 1:
            raise ValueError("inference_concurrency must be positive")
        key = (
            str(resolved_models_dir),
            json.dumps(model, sort_keys=True, default=str),
            str(resolved_cache_dir),
            threads,
            concurrency,
            modality_key,
        )
        with self._lock:
            provider = self._providers.get(key)
            if provider is None:
                provider = EmbeddingProvider(
                    model,
                    resolved_models_dir,
                    cache_dir=resolved_cache_dir,
                    threads=threads,
                    inference_concurrency=concurrency,
                    enabled_modalities=enabled_modalities,
                )
                self._providers[key] = provider
            return provider
