"""Build a blinded local listening pack for the 40-window speech A/B set."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import random
import wave
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_DIR = ROOT / "benchmarks" / "evaluation" / "iterative_speech_presence_natural"
DEFAULT_OUTPUT_DIR = ROOT / "benchmarks" / "review" / "iterative_speech_presence_natural"
SHUFFLE_SEED = 20_261_026


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_rows(path: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError(f"no evaluation rows found: {path}")
    for row in rows:
        if row.get("axis_id") != "speech_presence":
            raise ValueError("review pack only supports the speech_presence axis")
        if row.get("expected_candidate_id") not in {"speech_present", "speech_absent"}:
            raise ValueError("expected labels must be speech_present or speech_absent")
    return rows


def _extract_clip(eval_dir: Path, row: dict[str, Any]) -> tuple[bytes, int, int, int]:
    source_path = eval_dir / "inputs" / str(row["corpus_file"])
    with wave.open(str(source_path), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        sample_rate = source.getframerate()
        if sample_width != 2:
            raise ValueError(f"expected 16-bit PCM input: {source_path}")
        start_ms = int(row["start_ms"])
        end_ms = int(row["end_ms"])
        first_frame = round(start_ms * sample_rate / 1_000)
        frame_count = round((end_ms - start_ms) * sample_rate / 1_000)
        source.setpos(first_frame)
        frames = source.readframes(frame_count)
        if len(frames) != frame_count * channels * sample_width:
            raise ValueError(f"incomplete source interval in {source_path}: {row}")

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width)
        writer.setframerate(sample_rate)
        writer.writeframes(frames)
    return buffer.getvalue(), channels, sample_rate, end_ms - start_ms


def _write_player(player_dir: Path, clips: list[dict[str, Any]]) -> None:
    player_dir.mkdir(parents=True, exist_ok=True)
    clip_rows: list[str] = []
    for clip in clips:
        clip_id = html.escape(clip["clip_id"])
        clip_rows.append(
            "<tr>"
            f'<th scope="row">{clip_id}</th>'
            f'<td><audio controls preload="none" src="clips/{clip_id}.wav">'
            "В этом браузере аудио не воспроизводится.</audio></td>"
            f'<td><select aria-label="Разметка речи для {clip_id}" data-label>'
            '<option value="">Выберите</option>'
            '<option value="speech_present">Речь слышна</option>'
            '<option value="speech_absent">Речи нет</option>'
            '<option value="uncertain">Не уверен</option>'
            "</select></td>"
            f'<td><input type="text" aria-label="Заметки для {clip_id}" data-notes></td>'
            "</tr>"
        )
    document = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Независимая разметка речи</title>
  <style>
    :root { color-scheme: light dark; font: 16px/1.5 system-ui, sans-serif; }
    body { margin: 2rem auto; padding: 0 1rem; max-width: 1100px; }
    h1 { line-height: 1.15; }
    .hint { max-width: 72ch; }
    table { border-collapse: collapse; width: 100%; margin-top: 1.5rem; }
    th, td { border-bottom: 1px solid #8887; padding: .7rem .5rem; text-align: left; }
    th { position: sticky; top: 0; background: Canvas; }
    audio { width: min(100%, 420px); }
    select, input { font: inherit; padding: .35rem; }
    input { width: min(28vw, 220px); }
    button { font: inherit; margin: 1rem 0; padding: .65rem 1rem; }
    @media (max-width: 700px) { td:nth-child(2) { min-width: 210px; } }
  </style>
</head>
<body>
  <h1>Независимая разметка речи</h1>
  <p class="hint">Для каждого фрагмента длиной пять секунд отметьте, слышна ли человеческая
  речь. Учитывайте фоновую речь и речь на любом языке. Пение и хор речью не считаются.
  Выберите «Не уверен», если фрагмент слишком неоднозначен или неразборчив.</p>
  <p class="hint">ID фрагментов перемешаны и не содержат правильных ответов. Сначала закончите
  прослушивание и экспортируйте разметку, затем откройте отдельный файл answer key.</p>
  <button id="export" type="button">Скачать CSV с разметкой</button>
  <span id="status" role="status" aria-live="polite"></span>
  <table>
    <thead><tr><th>Фрагмент</th><th>Аудио</th><th>Разметка</th><th>Заметки</th></tr></thead>
    <tbody>
__ROWS__
    </tbody>
  </table>
  <script>
    const quote = value => '"' + value.replaceAll('"', '""') + '"';
    document.querySelector('#export').addEventListener('click', () => {
      const rows = [...document.querySelectorAll('tbody tr')].map(row => {
        const clipId = row.querySelector('th').textContent.trim();
        const label = row.querySelector('[data-label]').value;
        const notes = row.querySelector('[data-notes]').value;
        return {clipId, label, notes};
      });
      const missing = rows.filter(row => !row.label);
      if (missing.length) {
        document.querySelector('#status').textContent =
          `Осталось выбрать разметку для фрагментов: ${missing.length}.`;
        return;
      }
      const csv = ['clip_id,label,notes', ...rows.map(row =>
        [row.clipId, row.label, row.notes].map(quote).join(','))].join('\\r\\n');
      const link = document.createElement('a');
      link.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
      link.download = 'human_labels.csv';
      link.click();
      URL.revokeObjectURL(link.href);
      document.querySelector('#status').textContent = 'CSV с разметкой сохранён.';
    });
  </script>
</body>
</html>
""".replace("__ROWS__", "\n".join(clip_rows))
    (player_dir / "review.html").write_text(document, encoding="utf-8")


def build(eval_dir: Path, output_dir: Path, *, seed: int = SHUFFLE_SEED) -> dict[str, Any]:
    rows = _read_rows(eval_dir / "expected_segments.jsonl")
    random.Random(seed).shuffle(rows)
    player_dir = output_dir / "player"
    clips_dir = player_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    clip_metadata: list[dict[str, Any]] = []
    key_path = output_dir / "review_key" / "answer_key.csv"
    key_path.parent.mkdir(parents=True, exist_ok=True)

    with key_path.open("w", encoding="utf-8-sig", newline="") as key_file:
        fields = [
            "clip_id",
            "axis_id",
            "expected_candidate_id",
            "stream_id",
            "corpus_file",
            "start_ms",
            "end_ms",
            "source_file",
            "source_start_ms",
            "source_end_ms",
            "rationale",
            "clip_sha256",
        ]
        writer = csv.DictWriter(key_file, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            clip_id = f"clip-{index:03d}"
            payload, _channels, _sample_rate, duration_ms = _extract_clip(eval_dir, row)
            clip_path = clips_dir / f"{clip_id}.wav"
            clip_path.write_bytes(payload)
            clip_metadata.append({"clip_id": clip_id})
            key_record = {
                field: row.get(field, "")
                for field in fields
                if field not in {"clip_id", "clip_sha256"}
            }
            writer.writerow(
                {
                    "clip_id": clip_id,
                    **key_record,
                    "clip_sha256": _sha256(payload),
                }
            )
            if duration_ms != 5_000:
                raise ValueError(f"expected five-second evaluation clip: {clip_id}")

    _write_player(player_dir, clip_metadata)
    (output_dir / "README.md").write_text(
        "# Набор для слепой ручной разметки аудио\n\n"
        "Набор содержит 40 перемешанных фрагментов по пять секунд для оси `speech_presence`. "
        "Плеер не раскрывает метки или описания источников. Откройте "
        "`player/review.html`, прослушайте каждый фрагмент, выберите разметку и сохраните "
        "CSV. Файл `review_key/answer_key.csv` открывайте только после завершения разметки: "
        "в нём ID связаны с исходными интервалами и метками.\n\n"
        "`speech_present` — слышна человеческая речь, включая фоновый разговор; "
        "`speech_absent` — музыка, пение/хор или окружающий звук без речи; `uncertain` — "
        "надёжно определить нельзя. Фрагменты предназначены только для оценки и не являются "
        "обучающими данными. Источники, лицензии и хэши указаны в "
        "`review_key/provenance.md`.\n\n"
        "После экспорта выполните:\n\n"
        "```powershell\n"
        "python scripts/import_audio_review_labels.py human_labels.csv "
        "benchmarks/review/iterative_speech_presence_natural/review_key/answer_key.csv "
        "--output benchmarks/review/iterative_speech_presence_natural/reviewed_labels.jsonl\n"
        "python scripts/evaluate_iterative_hypotheses.py "
        "benchmarks/reports/iterative_speech_presence_natural/iterations.jsonl "
        "benchmarks/review/iterative_speech_presence_natural/reviewed_labels.jsonl "
        "--output benchmarks/review/iterative_speech_presence_natural/reviewed_evaluation.json\n"
        "```\n"
        "Разметки `uncertain` сохраняются в summary, но не участвуют в бинарном A/B scoring.\n",
        encoding="utf-8",
    )
    _write_provenance(eval_dir, output_dir)
    return {
        "clips": len(clip_metadata),
        "duration_ms_each": 5_000,
        "player": str((player_dir / "review.html").resolve()),
        "answer_key": str(key_path.resolve()),
    }


def _write_provenance(eval_dir: Path, output_dir: Path) -> None:
    manifest = json.loads((eval_dir / "manifest.json").read_text(encoding="utf-8"))
    lines = [
        "# Source provenance for the blinded speech review pack",
        "",
        "Open this file after the independent listening labels are complete.",
        "",
        "The excerpts are derived from the local evaluation corpus. The source file hashes "
        "below are from the corpus manifest; clip-specific hashes are in `answer_key.csv`.",
        "",
        "| Source | License / attribution | SHA-256 |",
        "|---|---|---|",
    ]
    for source in manifest.get("source_assets", []):
        title = source.get("source_title", source.get("file", ""))
        page = source.get("source_page", "")
        license_text = source.get("license", "")
        license_cell = f"[{license_text}]({page})" if page else license_text
        lines.append(
            f"| {title} | {license_cell} | `{source.get('sha256', '')}` |"
        )
    (output_dir / "review_key" / "provenance.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=SHUFFLE_SEED)
    args = parser.parse_args()
    result = build(args.eval_dir.resolve(), args.output_dir.resolve(), seed=args.seed)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
