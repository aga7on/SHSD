from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from shsd.models.artifacts import MissingModelFiles, verify_local_artifacts


def test_missing_model_files_fail_with_explicit_fetch_command(tmp_path: Path) -> None:
    model = {
        "file": "weights.gguf",
        "size_bytes": 10,
        "sha256": "0" * 64,
    }

    with pytest.raises(MissingModelFiles, match="download_models.py --model qwen3_0_6b"):
        verify_local_artifacts("qwen3_0_6b", model, tmp_path)


def test_local_model_files_must_match_the_lock(tmp_path: Path) -> None:
    payload = b"pinned local weights"
    model_dir = tmp_path / "tiny_model"
    model_dir.mkdir()
    (model_dir / "weights.bin").write_bytes(payload)
    model = {
        "files": [
            {
                "path": "weights.bin",
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ]
    }

    assert verify_local_artifacts("tiny_model", model, tmp_path) == {
        "weights.bin": hashlib.sha256(payload).hexdigest()
    }
