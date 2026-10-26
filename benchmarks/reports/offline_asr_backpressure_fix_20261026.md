# Offline ASR backpressure recheck

## Finding

The first 90-second file run emitted all five ASR windows as `dropped: load_critical`. In local-file mode, source lag is caused by the unpaced media pass, while speech ASR is itself required to advance the E watermark. Using that watermark lag to reject ASR could therefore keep the speech lane from clearing the lag that triggered the rejection.

## Change

For local files, the analyzer now buffers ASR windows in a bounded queue sized from known media duration, capped at 32 windows. It runs the buffered speech work after the main media pass and does not feed this offline backlog into the shared live-load controller. URL/live sources keep the existing shared admission policy and two-window deferred capacity. When the bounded offline buffer fills, excess windows still receive explicit dropped coverage.

## Recheck

Source: `benchmarks/fixtures/real_poc/tears_of_steel_120_210s.mp4`, 90,000 ms; CPU, four threads, five-second windows; Qwen narrator and GigaAM ASR enabled.

- Before the change: 93.711 s, five unique speech windows dropped with `load_critical`.
- After the change: 87.626 s, five unique windows reached `final`, all returned non-empty text, zero speech drops; C/E/D/R reached 90,000 ms.
- The returned transcript is raw GigaAM output and has not been independently scored for accuracy.
- The rerun emitted 17 L3 captions: eight Qwen generations repeat “Обнаружено заметное изменение изображения.” and nine source-only fallbacks repeat scene-cut or temporal-coincidence claims. This remains a narration-quality failure.
- Semantic matcher abstentions and L2 runtime-backpressure coverage remain. No similarity or margin threshold changed.

The tables are in `real_video_quality_asr_recheck_20261026/`; its report links to the raw UTF-8 timeline at `poc_real_90s_asr_recheck_20261026/timeline.jsonl`. The earlier baseline is in `real_video_quality_20261026/`.

## Verification

- `tests/unit/test_analyze.py::test_speech_opt_in_emits_revisions_without_changing_audio_observations` now also denies ASR admission through the shared controller and verifies local-file ASR still completes.
- `tests/unit/test_analyze.py tests/unit/test_asr_worker.py`: 23 passed.
- Ruff, `py_compile`, and Mypy on `src/shsd/analyze.py` passed. Mypy needed `--disable-error-code=import-untyped` because this environment lacks psutil stubs.
