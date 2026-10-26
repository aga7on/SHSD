"""Explicitly fetch and checksum model/runtime artifacts from models.lock.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "models.lock.json"
DEFAULT_OUTPUT = ROOT / "models"
CHUNK_SIZE = 1024 * 1024
REPORT_EVERY = 64 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch(url: str, target: Path, expected_size: int, expected_sha256: str) -> None:
    """Resume a pinned artifact download and publish it only after checksum validation."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    if target.exists():
        if target.stat().st_size == expected_size and _sha256(target) == expected_sha256:
            print(f"Verified cached artifact: {target}", flush=True)
            return
        raise RuntimeError(f"Existing artifact does not match the lockfile: {target}")

    if partial.exists():
        partial_size = partial.stat().st_size
        if partial_size == expected_size:
            if _sha256(partial) == expected_sha256:
                os.replace(partial, target)
                print(f"Verified cached artifact: {target}", flush=True)
                return
            partial.unlink()
        elif partial_size > expected_size:
            partial.unlink()
    print(f"Fetching {target.name} ({expected_size:,} bytes)", flush=True)
    for attempt in range(4):
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "SHSD-model-fetch/0.1"}
        headers["Range"] = f"bytes={offset}-"
        mode = "ab" if offset else "wb"
        started = time.monotonic()
        try:
            with requests.get(
                url,
                headers=headers,
                stream=True,
                timeout=(20, 90),
            ) as response:
                response.raise_for_status()
                status = response.status_code
                if offset and status != 206:
                    partial.unlink(missing_ok=True)
                    if attempt < 3:
                        continue
                    raise RuntimeError("Artifact server did not honor the resume range")
                content_range = response.headers.get("Content-Range")
                if status == 206 and content_range:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
                    if match is None or int(match.group(1)) != offset:
                        raise RuntimeError(f"Unexpected Content-Range: {content_range}")
                written = offset
                next_report = ((offset // REPORT_EVERY) + 1) * REPORT_EVERY
                with partial.open(mode) as destination:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        destination.write(chunk)
                        written += len(chunk)
                        if written >= next_report:
                            elapsed = max(time.monotonic() - started, 0.001)
                            rate_mib_s = (written - offset) / elapsed / (1024 * 1024)
                            print(
                                f"{target.name}: {written:,}/{expected_size:,} bytes "
                                f"({rate_mib_s:.1f} MiB/s)",
                                flush=True,
                            )
                            next_report += REPORT_EVERY
            break
        except requests.RequestException as error:
            if attempt == 3:
                raise RuntimeError(
                    f"Download interrupted after 4 resumable attempts: {error}"
                ) from error
            delay = min(2**attempt, 8)
            print(
                f"Connection interrupted; resuming {target.name} in {delay}s "
                f"(attempt {attempt + 2}/4)",
                flush=True,
            )
            time.sleep(delay)

    actual_size = partial.stat().st_size
    if actual_size != expected_size:
        raise RuntimeError(
            f"Incomplete artifact {target.name}: received {actual_size:,} of "
            f"{expected_size:,} bytes; rerun the command to resume"
        )
    actual_hash = _sha256(partial)
    if actual_hash != expected_sha256:
        partial.unlink(missing_ok=True)
        raise RuntimeError(
            f"SHA-256 mismatch for {target.name}: expected {expected_sha256}, got {actual_hash}"
        )
    os.replace(partial, target)
    print(f"Verified {target.name}: {actual_hash}", flush=True)


def _repo_url(repo_id: str, revision: str, filename: str) -> str:
    encoded_repo = "/".join(urllib.parse.quote(part, safe="") for part in repo_id.split("/"))
    encoded_filename = urllib.parse.quote(filename, safe="/")
    return f"https://huggingface.co/{encoded_repo}/resolve/{revision}/{encoded_filename}"


def _download_model(
    name: str,
    model: dict[str, Any],
    output_root: Path,
    *,
    metadata: bool,
    weights: bool,
) -> None:
    target_dir = output_root / name
    if metadata:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as error:
            message = "Install the project model dependencies before fetching metadata"
            raise RuntimeError(message) from error
        print(f"Fetching small pinned-revision metadata for {name}", flush=True)
        snapshot_download(
            repo_id=model["repo_id"],
            revision=model["revision"],
            local_dir=str(target_dir),
            allow_patterns=["*.json", "*.py", "*.jinja", "*.md", ".gitattributes"],
        )

    if not weights:
        return

    files = model.get("files")
    if files is None:
        files = [
            {
                "path": model["file"],
                "size_bytes": model["size_bytes"],
                "sha256": model["sha256"],
            }
        ]
    for artifact in files:
        filename = artifact["path"]
        url = _repo_url(model["repo_id"], model["revision"], filename)
        _fetch(
            url,
            target_dir / filename,
            artifact["size_bytes"],
            artifact["sha256"],
        )


def _download_runtime(name: str, runtime: dict[str, Any], output_root: Path) -> None:
    repo = runtime["repo"].split("/", maxsplit=1)
    url = (
        "https://github.com/"
        + "/".join(urllib.parse.quote(part, safe="") for part in repo)
        + "/releases/download/"
        + urllib.parse.quote(runtime["version"], safe="")
        + "/"
        + urllib.parse.quote(runtime["asset"], safe="")
    )
    archive = output_root / "runtimes" / name / runtime["version"] / runtime["asset"]
    _fetch(url, archive, runtime["size_bytes"], runtime["sha256"])

    extract_dir = archive.parent / "bin"
    extract_dir.mkdir(parents=True, exist_ok=True)
    root = extract_dir.resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            destination = (extract_dir / member.filename).resolve()
            if not destination.is_relative_to(root):
                raise RuntimeError(f"Unsafe path in runtime archive: {member.filename}")
        package.extractall(extract_dir)
    print(f"Extracted {name} runtime to {extract_dir}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--model", metavar="ID", help="model lock ID or 'all' to fetch every model"
    )
    selection.add_argument("--runtime", choices=["llama_cpp"])
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="fetch pinned repository metadata but skip the model weight files",
    )
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))

    if args.runtime:
        _download_runtime(args.runtime, lock["runtimes"][args.runtime], output_root)
        return 0

    models: dict[str, dict[str, Any]] = lock["models"]
    names = list(models) if args.model == "all" else [args.model]
    for name in names:
        if name not in models:
            parser.error(f"unknown model '{name}'; choose from: {', '.join(models)}")
        _download_model(
            name,
            models[name],
            output_root,
            metadata=not args.metadata_only and name != "qwen3_0_6b",
            weights=not args.metadata_only,
        )
    print(f"Model files stored under {output_root}; runtime loading remains local-only.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, requests.RequestException, zipfile.BadZipFile) as error:
        print(f"download failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
