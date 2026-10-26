from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from shsd.bridge.features import AVFeatureBatch


def _record(
    modality: str,
    *,
    interval_ms: tuple[int, int],
    frame_pts_ms: tuple[int, ...] = (),
    width: int = 3,
    attention_mask: tuple[bool, ...] = (True, True),
) -> SimpleNamespace:
    return SimpleNamespace(
        token_embeddings=np.ones((len(attention_mask), width), dtype=np.float32),
        attention_mask=np.asarray(attention_mask, dtype=np.bool_),
        input_token_ids=np.arange(len(attention_mask), dtype=np.int64),
        model_revision="encoder-rev-1",
        input_preprocess_version=f"{modality}-preprocess-v1",
        modality=modality,
        frame_pts_ms=frame_pts_ms,
        interval_ms=interval_ms,
    )


@pytest.mark.parametrize(
    ("mode", "frame_records", "audio_record", "expected_mask"),
    [
        (
            "IMAGE",
            (_record("image", interval_ms=(0, 1), frame_pts_ms=(0,)),),
            None,
            {"vision": True, "audio": False},
        ),
        (
            "VIDEO",
            (
                _record("image", interval_ms=(0, 1), frame_pts_ms=(0,)),
                _record("image", interval_ms=(500, 501), frame_pts_ms=(500,)),
            ),
            None,
            {"vision": True, "audio": False},
        ),
        ("AUDIO", (), _record("audio", interval_ms=(0, 1000)), {"vision": False, "audio": True}),
        (
            "AV",
            (_record("image", interval_ms=(0, 1), frame_pts_ms=(0,)),),
            _record("audio", interval_ms=(0, 1000)),
            {"vision": True, "audio": True},
        ),
    ],
)
def test_av_feature_batch_preserves_pts_and_missing_modality_masks(
    mode: str,
    frame_records: tuple[SimpleNamespace, ...],
    audio_record: SimpleNamespace | None,
    expected_mask: dict[str, bool],
) -> None:
    batch = AVFeatureBatch.from_records(
        mode=mode,  # type: ignore[arg-type]
        source_id="source-1",
        epoch=0,
        interval_ms=(0, 1000),
        frame_records=frame_records,  # type: ignore[arg-type]
        audio_record=audio_record,  # type: ignore[arg-type]
    )

    assert batch.modality_present == expected_mask
    assert batch.metadata()["frame_pts_ms"] == [record.frame_pts_ms[0] for record in frame_records]
    assert batch.metadata()["interval_ms"] == [0, 1000]


def test_av_feature_batch_rejects_out_of_order_pts() -> None:
    records = (
        _record("image", interval_ms=(500, 501), frame_pts_ms=(500,)),
        _record("image", interval_ms=(100, 101), frame_pts_ms=(100,)),
    )

    with pytest.raises(ValueError, match="strictly increasing"):
        AVFeatureBatch.from_records(
            mode="VIDEO",
            source_id="source-1",
            epoch=0,
            interval_ms=(0, 1000),
            frame_records=records,  # type: ignore[arg-type]
        )


def test_frame_record_must_be_one_image_at_its_exact_pts() -> None:
    with pytest.raises(ValueError, match="one IMAGE sequence"):
        AVFeatureBatch.from_records(
            mode="IMAGE",
            source_id="source-1",
            epoch=0,
            interval_ms=(0, 1000),
            frame_records=(_record("video", interval_ms=(0, 1), frame_pts_ms=(0,)),),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="identify its source PTS"):
        AVFeatureBatch.from_records(
            mode="IMAGE",
            source_id="source-1",
            epoch=0,
            interval_ms=(0, 1000),
            frame_records=(_record("image", interval_ms=(1, 2), frame_pts_ms=(0,)),),  # type: ignore[arg-type]
        )


def test_audio_interval_must_match_batch_and_widths_must_match() -> None:
    frame = _record("image", interval_ms=(0, 1), frame_pts_ms=(0,))
    with pytest.raises(ValueError, match="must match the batch"):
        AVFeatureBatch.from_records(
            mode="AV",
            source_id="source-1",
            epoch=0,
            interval_ms=(0, 1000),
            frame_records=(frame,),  # type: ignore[arg-type]
            audio_record=_record("audio", interval_ms=(0, 900)),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="feature width"):
        AVFeatureBatch.from_records(
            mode="AV",
            source_id="source-1",
            epoch=0,
            interval_ms=(0, 1000),
            frame_records=(frame,),  # type: ignore[arg-type]
            audio_record=_record("audio", interval_ms=(0, 1000), width=4),  # type: ignore[arg-type]
        )


def test_token_sequence_rejects_empty_attention_mask_and_non_finite_values() -> None:
    with pytest.raises(ValueError, match="at least one active token"):
        AVFeatureBatch.from_records(
            mode="IMAGE",
            source_id="source-1",
            epoch=0,
            interval_ms=(0, 1000),
            frame_records=(
                _record(
                    "image",
                    interval_ms=(0, 1),
                    frame_pts_ms=(0,),
                    attention_mask=(False, False),
                ),
            ),  # type: ignore[arg-type]
        )
    record = _record("image", interval_ms=(0, 1), frame_pts_ms=(0,))
    record.token_embeddings[0, 0] = np.nan
    with pytest.raises(ValueError, match="must be finite"):
        AVFeatureBatch.from_records(
            mode="IMAGE",
            source_id="source-1",
            epoch=0,
            interval_ms=(0, 1000),
            frame_records=(record,),  # type: ignore[arg-type]
        )
