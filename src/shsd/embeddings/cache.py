"""Small, fingerprinted disk cache for normalized 768-dimensional vectors."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import cast

import numpy as np

EMBEDDING_DIM = 768


def normalize_embedding(vector: np.ndarray) -> np.ndarray:
    """Validate and L2-normalize a single float32 embedding vector."""
    output = np.asarray(vector, dtype=np.float32).reshape(-1)
    if output.shape != (EMBEDDING_DIM,) or not np.isfinite(output).all():
        raise ValueError(f"expected a finite float32[{EMBEDDING_DIM}] embedding")
    norm = float(np.linalg.norm(output))
    if norm <= 1e-12:
        raise ValueError("embedding vector must have a non-zero norm")
    normalized = output.copy() if abs(norm - 1.0) <= 1e-6 else output / norm
    normalized.setflags(write=False)
    return normalized


class DiskEmbeddingCache:
    """Atomic `.npy` cache; keys are hashes of model and preprocessing fingerprints."""

    def __init__(self, directory: Path, *, max_bytes: int = 512 * 1024 * 1024) -> None:
        if max_bytes < EMBEDDING_DIM * 4:
            raise ValueError("max_bytes must fit at least one embedding")
        self.directory = directory
        self.max_bytes = max_bytes
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(*, model_revision: str, preprocess_version: str, modality: str, content: bytes) -> str:
        digest = hashlib.sha256()
        for value in (model_revision, preprocess_version, modality):
            digest.update(value.encode("utf-8"))
            digest.update(b"\0")
        digest.update(content)
        return digest.hexdigest()

    def _path(self, key: str) -> Path:
        if re.fullmatch(r"[0-9a-f]{64}", key) is None:
            raise ValueError("cache key must be a lowercase SHA-256 digest")
        return self.directory / f"{key}.npy"

    def get(self, key: str) -> np.ndarray | None:
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            vector = normalize_embedding(cast(np.ndarray, np.load(path, allow_pickle=False)))
        except (OSError, ValueError):
            return None
        os.utime(path, None)
        return vector

    def put(self, key: str, vector: np.ndarray) -> None:
        path = self._path(key)
        normalized = normalize_embedding(vector)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=self.directory, prefix=".embedding-", suffix=".tmp", delete=False
            ) as temporary:
                temporary_name = temporary.name
                np.save(temporary, normalized, allow_pickle=False)
            os.replace(temporary_name, path)
            temporary_name = None
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
        self._evict(except_path=path)

    def _evict(self, *, except_path: Path) -> None:
        files = list(self.directory.glob("*.npy"))
        total = sum(path.stat().st_size for path in files)
        if total <= self.max_bytes:
            return
        for path in sorted(files, key=lambda item: item.stat().st_mtime_ns):
            if path == except_path:
                continue
            total -= path.stat().st_size
            path.unlink(missing_ok=True)
            if total <= self.max_bytes:
                return
