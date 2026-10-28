"""Verify that local model artifacts match the pinned entries in models.lock.json.

Runtime stays fully offline: nothing here downloads. A mismatch or a missing file
raises :class:`MissingModelFiles`, whose message states the explicit fetch command.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

CHUNK_SIZE = 1024 * 1024
FETCH_COMMAND = "python scripts/download_models.py --model {name}"
RUNTIME_COMMAND = "python scripts/download_models.py --runtime {name}"

# (path, size, mtime_ns) -> sha256, so a long run hashes multi-GB weights only once.
_HASH_CACHE: dict[tuple[str, int, int], str] = {}


class MissingModelFiles(RuntimeError):
    """Raised when local model/runtime files are absent or do not match the lock."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cached_sha256(path: Path, size: int) -> str:
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    cached = _HASH_CACHE.get(key)
    if cached is not None and stat.st_size == size:
        return cached
    digest = _sha256(path)
    _HASH_CACHE[key] = digest
    return digest


def declared_files(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a lock entry into a list of ``path``/``size_bytes``/``sha256`` records."""
    files = model.get("files")
    if files is not None:
        return [dict(artifact) for artifact in files]
    return [
        {
            "path": model["file"],
            "size_bytes": model["size_bytes"],
            "sha256": model["sha256"],
        }
    ]


def verify_local_artifacts(
    name: str,
    model: dict[str, Any],
    models_dir: Path,
) -> dict[str, str]:
    """Check every declared file under ``models_dir/name`` and return path -> sha256.

    Only files whose size and SHA-256 both match the lock entry are reported. Any
    missing, truncated, or altered artifact raises :class:`MissingModelFiles` with
    the exact command that fetches it again.
    """
    root = Path(models_dir)
    problems: list[str] = []
    verified: dict[str, str] = {}

    if not declared_files(model):
        problems.append("the lock entry declares no files")

    for artifact in declared_files(model):
        relative = str(artifact["path"])
        target = root / name / relative
        expected_size = int(artifact["size_bytes"])
        expected_sha256 = str(artifact["sha256"]).lower()
        if not target.is_file():
            problems.append(f"missing {name}/{relative}")
            continue
        actual_size = target.stat().st_size
        if actual_size != expected_size:
            problems.append(
                f"{name}/{relative} has {actual_size:,} bytes, expected {expected_size:,}"
            )
            continue
        actual_sha256 = _cached_sha256(target, expected_size)
        if actual_sha256 != expected_sha256:
            problems.append(
                f"{name}/{relative} sha256 {actual_sha256} does not match {expected_sha256}"
            )
            continue
        verified[relative] = actual_sha256

    if problems:
        command = RUNTIME_COMMAND.format(name=name)
        if name not in {"llama_cpp"}:
            command = FETCH_COMMAND.format(name=name)
        details = "; ".join(problems)
        raise MissingModelFiles(
            f"local artifacts for {name} are unavailable ({details}). "
            f"Fetch them explicitly with: {command}"
        )

    return verified
