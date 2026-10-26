from __future__ import annotations

import hashlib
import json
from pathlib import Path

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures"


def test_generated_fixture_manifest_is_local_complete_and_checksummed() -> None:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assets = manifest["assets"]

    assert manifest["network_required"] is False
    assert 5 <= len(assets) <= 10
    filenames = {asset["file"] for asset in assets}
    assert {
        "av_sync_20s.mp4",
        "av_sync_20s.mkv",
        "audio_speech_ru.wav",
        "audio_silence_5s.wav",
        "video_motion_8s.mp4",
        "video_scene_cuts_8s.mp4",
    } <= filenames

    for asset in assets:
        media_path = FIXTURE_ROOT / "media" / asset["file"]
        payload = media_path.read_bytes()
        assert len(payload) == asset["bytes"]
        assert hashlib.sha256(payload).hexdigest() == asset["sha256"]
        assert asset["expected_intervals_ms"]
        assert all(
            interval["start_ms"] < interval["end_ms"]
            for interval in asset["expected_intervals_ms"]
        )


def test_av_fixture_labels_expected_half_open_intervals() -> None:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    av_asset = next(asset for asset in manifest["assets"] if asset["file"] == "av_sync_20s.mp4")

    assert av_asset["duration_ms"] == 20_000
    assert [
        (interval["start_ms"], interval["end_ms"])
        for interval in av_asset["expected_intervals_ms"]
    ] == [(0, 5000), (5000, 10000), (10000, 15000), (15000, 20000)]
    assert "real music" in av_asset["must_not_claim"]


def test_audio_only_and_video_only_fixtures_declare_available_tracks() -> None:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    track_types = {
        asset["file"]: {stream["codec_type"] for stream in asset["streams"]}
        for asset in manifest["assets"]
    }

    assert track_types["audio_speech_ru.wav"] == {"audio"}
    assert track_types["audio_silence_5s.wav"] == {"audio"}
    assert track_types["video_motion_8s.mp4"] == {"video"}
    assert track_types["video_static_3s.mp4"] == {"video"}
