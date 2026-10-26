"""Generate small, synthetic SHSD audio/video fixtures without network access."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "tests" / "fixtures" / "media"
MANIFEST_NAME = "manifest.json"
WIDTH = 320
HEIGHT = 180
VIDEO_FPS = 10
SAMPLE_RATE = 48_000


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"Required local program '{name}' was not found on PATH")
    return path


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


def _lavfi_audio(ffmpeg: str, path: Path, source: str, duration_s: int) -> None:
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            source,
            "-t",
            str(duration_s),
            "-vn",
            "-c:a",
            "pcm_s16le",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "1",
            str(path),
        ]
    )


def _lavfi_video(ffmpeg: str, path: Path, source: str, duration_s: int) -> None:
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            source,
            "-t",
            str(duration_s),
            "-an",
            "-c:v",
            "mpeg4",
            "-q:v",
            "5",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
    )


def _scene_inputs(colors: list[str], duration_s: int) -> tuple[list[str], str]:
    args: list[str] = []
    filters: list[str] = []
    for index, color in enumerate(colors):
        args.extend(
            [
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s={WIDTH}x{HEIGHT}:r={VIDEO_FPS}:d={duration_s}",
            ]
        )
        filters.append(f"[{index}:v]")
    graph = "".join(filters) + f"concat=n={len(colors)}:v=1:a=0[vout]"
    return args, graph


def _generate_av_sync(ffmpeg: str, path: Path, *, matroska: bool = False) -> None:
    colors = ["0x23395d", "0x345b47", "0x803d3d", "0x5b477f"]
    inputs, video_graph = _scene_inputs(colors, duration_s=5)
    # The two active tone intervals line up with the second and fourth scenes.
    audio_expression = (
        "if(lt(t,5),0,"
        "if(lt(t,10),(0.18*sin(2*PI*440*t)+0.08*sin(2*PI*660*t))"
        "*(0.55+0.45*sin(2*PI*2*t)),"
        "if(lt(t,15),0,0.16*sin(2*PI*330*t)"
        "*(0.5+0.5*sin(2*PI*2*t)))))"
    )
    graph = (
        video_graph
        + ";"
        + f"aevalsrc=exprs='{audio_expression}':s={SAMPLE_RATE}:d=20[aout]"
    )
    command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *inputs,
            "-filter_complex",
            graph,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-t",
            "20",
            "-c:v",
            "mpeg4",
            "-q:v",
            "5",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "flac" if matroska else "aac",
        ]
    if not matroska:
        command.extend(
            ["-b:a", "64k", "-video_track_timescale", "90000", "-movflags", "+faststart"]
        )
    command.append(str(path))
    _run(command)


def _generate_scene_cuts(ffmpeg: str, path: Path) -> None:
    inputs, graph = _scene_inputs(
        ["0x23395d", "0x345b47", "0x803d3d", "0x5b477f"], duration_s=2
    )
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *inputs,
            "-filter_complex",
            graph,
            "-map",
            "[vout]",
            "-an",
            "-c:v",
            "mpeg4",
            "-q:v",
            "5",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
    )


def _generate_speech(espeak: str, path: Path) -> tuple[str, str]:
    text = "Это короткая синтетическая русская речь для проверки временных меток."
    text_path = path.with_suffix(".txt")
    text_path.write_text(text, encoding="utf-8")
    try:
        _run([espeak, "-v", "ru", "-s", "135", "-f", str(text_path), "-w", str(path)])
    finally:
        text_path.unlink(missing_ok=True)
    version = subprocess.run(
        [espeak, "--version"], check=True, capture_output=True, text=True
    ).stdout.splitlines()[0]
    return text, version


def _probe(ffprobe: str, path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type,codec_name,time_base,start_pts,start_time,duration_ts,duration,width,height,sample_rate,channels",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _duration_ms(probe: dict[str, Any]) -> int:
    raw = probe.get("format", {}).get("duration")
    if raw is None:
        raise RuntimeError("ffprobe did not report a container duration")
    duration = Fraction(raw) * 1000
    quotient, remainder = divmod(abs(duration.numerator), duration.denominator)
    if remainder * 2 >= duration.denominator:
        quotient += 1
    return quotient


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset(
    ffprobe: str,
    path: Path,
    *,
    labels: list[dict[str, Any]],
    source: str,
    must_not_claim: list[str],
) -> dict[str, Any]:
    probe = _probe(ffprobe, path)
    return {
        "file": path.name,
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "duration_ms": _duration_ms(probe),
        "streams": probe.get("streams", []),
        "expected_intervals_ms": labels,
        "manual_label": source,
        "must_not_claim": must_not_claim,
    }


def generate(output_dir: Path = DEFAULT_OUTPUT) -> Path:
    """Create nine short synthetic fixtures and their timing/license manifest."""
    ffmpeg = _tool("ffmpeg")
    ffprobe = _tool("ffprobe")
    espeak = _tool("espeak-ng")
    output_dir.mkdir(parents=True, exist_ok=True)

    av_path = output_dir / "av_sync_20s.mp4"
    _generate_av_sync(ffmpeg, av_path)
    mkv_path = output_dir / "av_sync_20s.mkv"
    _generate_av_sync(ffmpeg, mkv_path, matroska=True)

    music_path = output_dir / "audio_music_10s.wav"
    _lavfi_audio(
        ffmpeg,
        music_path,
        "aevalsrc=exprs='(0.18*sin(2*PI*440*t)+0.08*sin(2*PI*660*t))"
        "*(0.55+0.45*sin(2*PI*2*t))':s=48000:d=10",
        10,
    )
    silence_path = output_dir / "audio_silence_5s.wav"
    _lavfi_audio(ffmpeg, silence_path, "anullsrc=r=48000:cl=mono", 5)
    sine_path = output_dir / "audio_sine_5s.wav"
    _lavfi_audio(ffmpeg, sine_path, "sine=frequency=440:sample_rate=48000", 5)

    speech_path = output_dir / "audio_speech_ru.wav"
    speech_text, speech_version = _generate_speech(espeak, speech_path)

    motion_path = output_dir / "video_motion_8s.mp4"
    _lavfi_video(
        ffmpeg,
        motion_path,
        f"testsrc2=s={WIDTH}x{HEIGHT}:r={VIDEO_FPS}:d=8",
        8,
    )
    scenes_path = output_dir / "video_scene_cuts_8s.mp4"
    _generate_scene_cuts(ffmpeg, scenes_path)
    static_path = output_dir / "video_static_3s.mp4"
    _lavfi_video(
        ffmpeg,
        static_path,
        f"color=c=0x456b82:s={WIDTH}x{HEIGHT}:r={VIDEO_FPS}:d=3",
        3,
    )

    av_labels: list[dict[str, Any]] = []
    for start_ms, end_ms, label in [
        (0, 5_000, "video: solid blue-gray scene; audio: digital silence"),
        (5_000, 10_000, "video: solid green scene; audio: two harmonic tones, pulsed"),
        (10_000, 15_000, "video: solid red scene; audio: digital silence"),
        (15_000, 20_000, "video: solid purple scene; audio: pulsed 330 Hz tone"),
    ]:
        av_labels.append(
            {"start_ms": start_ms, "end_ms": end_ms, "tracks": ["audio", "video"], "label": label}
        )

    assets = [
        _asset(
            ffprobe,
            av_path,
            labels=av_labels,
            source="Synthetic audiovisual PTS fixture generated with FFmpeg lavfi.",
            must_not_claim=["speech", "real music", "real scene semantics"],
        ),
        _asset(
            ffprobe,
            mkv_path,
            labels=av_labels,
            source="Synthetic audiovisual PTS fixture generated with FFmpeg lavfi in Matroska.",
            must_not_claim=["speech", "real music", "real scene semantics"],
        ),
        _asset(
            ffprobe,
            music_path,
            labels=[
                {
                    "start_ms": 0,
                    "end_ms": 10_000,
                    "tracks": ["audio"],
                    "label": "synthetic 440/660 Hz tones with 2 Hz amplitude modulation",
                }
            ],
            source="Synthetic signal generated with FFmpeg lavfi; not a recording or music sample.",
            must_not_claim=["real music", "specific instrument", "tonality"],
        ),
        _asset(
            ffprobe,
            speech_path,
            labels=[
                {
                    "start_ms": 0,
                    "end_ms": _duration_ms(_probe(ffprobe, speech_path)),
                    "tracks": ["audio"],
                    "label": "Russian synthetic speech: " + speech_text,
                }
            ],
            source=(
                "Synthetic speech generated locally with "
                + speech_version
                + " and the Russian voice; the TTS engine is not bundled."
            ),
            must_not_claim=["natural speaker", "speaker identity", "emotion"],
        ),
        _asset(
            ffprobe,
            silence_path,
            labels=[
                {"start_ms": 0, "end_ms": 5_000, "tracks": ["audio"], "label": "digital silence"}
            ],
            source="Zero-valued synthetic PCM generated with FFmpeg lavfi.",
            must_not_claim=["speech", "music", "environmental sound"],
        ),
        _asset(
            ffprobe,
            sine_path,
            labels=[
                {"start_ms": 0, "end_ms": 5_000, "tracks": ["audio"], "label": "440 Hz sine wave"}
            ],
            source="Synthetic sine wave generated with FFmpeg lavfi.",
            must_not_claim=["speech", "music", "instrument"],
        ),
        _asset(
            ffprobe,
            motion_path,
            labels=[
                {
                    "start_ms": 0,
                    "end_ms": 8_000,
                    "tracks": ["video"],
                    "label": "moving test pattern",
                }
            ],
            source="Synthetic moving test pattern generated with FFmpeg lavfi.",
            must_not_claim=["people", "objects", "real scene semantics", "audio"],
        ),
        _asset(
            ffprobe,
            scenes_path,
            labels=[
                {"start_ms": start, "end_ms": end, "tracks": ["video"], "label": label}
                for start, end, label in [
                    (0, 2_000, "blue-gray solid scene"),
                    (2_000, 4_000, "green solid scene"),
                    (4_000, 6_000, "red solid scene"),
                    (6_000, 8_000, "purple solid scene"),
                ]
            ],
            source="Synthetic scene cuts generated with FFmpeg lavfi.",
            must_not_claim=["people", "objects", "real scene semantics", "audio"],
        ),
        _asset(
            ffprobe,
            static_path,
            labels=[
                {"start_ms": 0, "end_ms": 3_000, "tracks": ["video"], "label": "static solid scene"}
            ],
            source="Synthetic static video generated with FFmpeg lavfi.",
            must_not_claim=["motion", "people", "audio"],
        ),
    ]
    manifest = {
        "schema_version": 1,
        "generated_by": "scripts/generate_fixtures.py",
        "network_required": False,
        "ffmpeg_version": subprocess.run(
            [ffmpeg, "-version"], check=True, capture_output=True, text=True
        ).stdout.splitlines()[0],
        "speech_generator": speech_version,
        "license": "Synthetic local test media; no third-party source recordings.",
        "assets": assets,
    }
    manifest_path = output_dir.parent / MANIFEST_NAME
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="directory for generated media (default: tests/fixtures/media)",
    )
    args = parser.parse_args()
    manifest = generate(args.output_dir.resolve())
    print(f"Generated 9 synthetic fixtures; manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
