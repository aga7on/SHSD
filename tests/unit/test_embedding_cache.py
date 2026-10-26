from __future__ import annotations

import numpy as np
import pytest

from shsd.embeddings.cache import EMBEDDING_DIM, DiskEmbeddingCache, normalize_embedding


def test_disk_cache_round_trips_normalized_vectors(tmp_path) -> None:
    cache = DiskEmbeddingCache(tmp_path / "vectors")
    key = cache.key(
        model_revision="revision-a",
        preprocess_version="prep-v1",
        modality="text",
        content=b"candidate sentence",
    )

    assert cache.get(key) is None
    cache.put(key, np.full(EMBEDDING_DIM, 2.0, dtype=np.float32))
    actual = cache.get(key)

    assert actual is not None
    assert actual.shape == (EMBEDDING_DIM,)
    assert float(np.linalg.norm(actual)) == pytest.approx(1.0)
    assert not actual.flags.writeable


def test_normalization_is_idempotent_for_cache_hits() -> None:
    source = np.linspace(-1.0, 1.0, EMBEDDING_DIM, dtype=np.float32)
    normalized = normalize_embedding(source)
    repeated = normalize_embedding(normalized)

    np.testing.assert_array_equal(repeated, normalized)


def test_cache_fingerprint_changes_with_model_or_preprocessing(tmp_path) -> None:
    cache = DiskEmbeddingCache(tmp_path)
    base = cache.key(
        model_revision="revision-a",
        preprocess_version="prep-v1",
        modality="image",
        content=b"frame",
    )

    assert base != cache.key(
        model_revision="revision-b",
        preprocess_version="prep-v1",
        modality="image",
        content=b"frame",
    )
    assert base != cache.key(
        model_revision="revision-a",
        preprocess_version="prep-v2",
        modality="image",
        content=b"frame",
    )


def test_cache_evicts_old_vectors_to_respect_disk_bound(tmp_path) -> None:
    cache = DiskEmbeddingCache(tmp_path, max_bytes=3500)
    first = cache.key(
        model_revision="r1", preprocess_version="p1", modality="text", content=b"first"
    )
    second = cache.key(
        model_revision="r1", preprocess_version="p1", modality="text", content=b"second"
    )
    vector = np.ones(EMBEDDING_DIM, dtype=np.float32)
    cache.put(first, vector)
    cache.put(second, vector)

    assert cache.get(first) is None
    assert cache.get(second) is not None


def test_zero_or_invalid_embedding_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-zero"):
        normalize_embedding(np.zeros(EMBEDDING_DIM, dtype=np.float32))
    with pytest.raises(ValueError, match="finite"):
        normalize_embedding(np.full(EMBEDDING_DIM, np.nan, dtype=np.float32))
