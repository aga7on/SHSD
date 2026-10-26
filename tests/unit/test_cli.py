from __future__ import annotations

import json
from pathlib import Path

import pytest

from shsd import __version__
from shsd.cli import main


def test_package_import_exposes_version() -> None:
    assert __version__ == "0.1.0"


def test_cli_without_arguments_displays_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: shsd" in capsys.readouterr().out


def test_cli_rejects_unknown_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["not-a-command"])

    assert error.value.code == 2
    assert "invalid choice: 'not-a-command'" in capsys.readouterr().err


def test_cli_analyze_validates_levels_before_loading_models(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "media" / "av_sync_20s.mkv"
    with pytest.raises(SystemExit) as error:
        main(["analyze", str(fixture), "--cpu-only", "--levels", "L4"])

    assert error.value.code == 2
    assert "analyze --levels accepts L0, L1, L2, and/or L3" in capsys.readouterr().err


def test_cli_analyze_help_exposes_cache_override(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["analyze", "--help"])

    assert error.value.code == 0
    help_text = capsys.readouterr().out
    assert "--cache-dir" in help_text
    assert "--prefetch-overflow-policy" in help_text
    assert "--prefetch-capacity" in help_text


def test_cli_analyze_rejects_unknown_prefetch_overflow_policy(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "media" / "av_sync_20s.mkv"

    with pytest.raises(SystemExit) as error:
        main(
            [
                "analyze",
                str(fixture),
                "--cpu-only",
                "--prefetch-overflow-policy",
                "discard-everything",
            ]
        )

    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_cli_analyze_requires_positive_prefetch_capacity(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "media" / "av_sync_20s.mkv"

    with pytest.raises(SystemExit) as error:
        main(["analyze", str(fixture), "--cpu-only", "--prefetch-capacity", "0"])

    assert error.value.code == 2
    assert "--prefetch-capacity must be positive" in capsys.readouterr().err


def test_cli_fast_replay_prints_media_summary(capsys: pytest.CaptureFixture[str]) -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "media" / "av_sync_20s.mkv"

    assert main(["replay", str(fixture), "--fast", "--stream-id", "cli-test"]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["stream_id"] == "cli-test"
    assert result["mode"] == "fast"
    assert result["packets_by_modality"]["audio"] > 0
    assert result["packets_by_modality"]["video"] > 0
    assert result["epoch"] == 0
