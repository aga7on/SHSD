from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import numpy as np
import pytest

torch = pytest.importorskip(
    "torch", reason="sequence-embedding tests need the optional torch runtime"
)

from shsd.embeddings.provider import (  # noqa: E402
    JOINT_PREPROCESS_VERSION,
    PREPROCESS_VERSION,
    VIDEO_PREPROCESS_VERSION,
    EmbeddingProvider,
    _load_video_sample,
    _video_input,
)

ROOT = Path(__file__).resolve().parents[2]


def test_video_timestamp_preprocessing_does_not_invalidate_audio_cache_version() -> None:
    class KeyCache:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def key(self, **kwargs: Any) -> str:
            self.calls.append(kwargs)
            return str(len(self.calls))

    provider = EmbeddingProvider.__new__(EmbeddingProvider)
    provider.cache = KeyCache()
    provider._revision = "test-revision"

    provider._cache_key("audio", b"audio")
    provider._cache_key(
        "video", b"video", preprocess_version=VIDEO_PREPROCESS_VERSION
    )
    provider._cache_key(
        "joint", b"av", preprocess_version=JOINT_PREPROCESS_VERSION
    )
    audio_key, video_key, joint_key = provider.cache.calls

    assert PREPROCESS_VERSION == "embeddinggemma2-st-v4-audio-video-metadata"
    assert audio_key["preprocess_version"] == PREPROCESS_VERSION
    assert video_key["preprocess_version"] == "embeddinggemma2-st-v5-video-source-pts"
    assert joint_key["preprocess_version"] == "embeddinggemma2-st-v5-av-source-pts"


def test_sequence_encoder_returns_unpooled_tokens_masks_and_source_pts() -> None:
    class HookHandle:
        def __init__(self, module: FakeTransformer) -> None:
            self.module = module

        def remove(self) -> None:
            self.module.hook = None

    class FakeTransformer:
        def __init__(self) -> None:
            self.hook: Any = None

        def register_forward_hook(self, hook: Any) -> HookHandle:
            self.hook = hook
            return HookHandle(self)

    class FakeEncoder:
        def __init__(self) -> None:
            self.transformer = FakeTransformer()
            self.seen_inputs: Any = None
            self.seen_kwargs: dict[str, Any] = {}

        def __getitem__(self, index: int) -> FakeTransformer:
            assert index == 0
            return self.transformer

        def encode(self, inputs: Any, **kwargs: Any) -> np.ndarray:
            self.seen_inputs = inputs
            self.seen_kwargs = kwargs
            output = {
                "token_embeddings": torch.ones((1, 3, 768), dtype=torch.bfloat16),
                "attention_mask": torch.tensor([[1, 1, 0]], dtype=torch.long),
                "input_ids": torch.tensor([[11, 12, 0]], dtype=torch.long),
                "video_position_ids": torch.zeros((2, 4, 2), dtype=torch.long),
            }
            self.transformer.hook(self.transformer, (), output)
            return np.zeros((1, 768), dtype=np.float32)

    provider = EmbeddingProvider.__new__(EmbeddingProvider)
    provider.encoder = FakeEncoder()
    provider._inference_lock = threading.Lock()
    provider._torch = torch
    provider._revision = "test-revision"

    pts_ms = (1000, 2250)
    record = provider._encode_sequence(
        _video_input(["frame-1", "frame-2"], {"frames_indices": [10, 22]}),
        modality="video",
        interval_ms=(1000, 3000),
        frame_pts_ms=pts_ms,
        video_metadata={"frames_indices": [10, 22]},
        processing_kwargs={"video": {"add_timestamps": True}},
    )

    assert record.token_embeddings.shape == (3, 768)
    assert record.attention_mask.tolist() == [True, True, False]
    assert record.input_token_ids is not None
    assert record.input_token_ids.tolist() == [11, 12, 0]
    assert record.frame_pts_ms == pts_ms
    assert record.video_metadata == {"frames_indices": [10, 22]}
    assert record.encoder_metadata["video_position_ids"].shape == (2, 4, 2)
    assert not record.token_embeddings.flags.writeable
    assert provider.encoder.transformer.hook is None
    assert provider.encoder.seen_kwargs["processing_kwargs"]["video"]["add_timestamps"]
    assert "token_embeddings" not in record.to_dict()
    assert record.to_dict(include_features=True)["token_embeddings"][0][0] == 1.0


def test_sampled_video_frames_keep_source_pts_and_timestamp_metadata() -> None:
    video_path = ROOT / "tests" / "fixtures" / "media" / "video_scene_cuts_8s.mp4"

    frames, pts_ms, metadata = _load_video_sample(
        video_path,
        interval_ms=(0, 5000),
        max_frames=4,
    )

    assert len(frames) == len(pts_ms) == 4
    assert pts_ms == (0, 1300, 2500, 3800)
    assert metadata["total_num_frames"] == 80
    assert metadata["fps"] == 10.0
    assert metadata["frames_indices"] == [0, 13, 25, 38]
    model_input = _video_input(frames, metadata)
    assert model_input["video"]["video_metadata"] == metadata
