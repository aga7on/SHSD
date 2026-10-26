# Todo.md — план реализации SHSD PoC

> Версия `0.1` · 25.10.2026 · Статус: **план, работа не отмечена выполненной**.  
> Архитектура: [Workspace.md](./Workspace.md). Правила работы агентов: [Agents.md](./Agents.md).

## 0. Обязательные условия

- [ ] **Не обучать** EmbeddingGemma 2, Qwen или любые projector/адаптеры в рамках v0.
- [ ] **Не собирать обучающий датасет**. Допускаются небольшие собственные/разрешённые **инженерные тестовые клипы** и фикстуры для тестов, без fine-tuning.
- [ ] **Целевой runtime только CPU**, интернет не должен требоваться после загрузки весов.
- [ ] Использовать реальные эмбеддинги EmbeddingGemma 2, не «генерировать» текст напрямую из её 768d тензора.
- [ ] Публиковать L1/L2 до L3 и не блокировать ingestion генерацией Qwen.
- [ ] Никакие факты о музыке, инструментах, голосах и видео не должны появляться в L3 без источников в L1/L2/ASR/DSP.
- [ ] Не обещать realtime до измерения RTF на целевом CPU.
- [ ] Все вычислительные оптимизации добавлять **после** корректной базовой реализации.

## 1. Правила ведения задач

**Формат ID:** `F0.01`, `F1.03`, ...; `F` означает фазу реализации. Поле `Depends` ниже задаёт явные зависимости. **Checkbox отмечать только после прохождения `DoD`** и фиксации доказательства (тест/скриншот/benchmark, PR/commit).

**Приоритеты:** `P0` блокирует работу; `P1` нужен для PoC; `P2` улучшение; `P3` эксперимент.

**Единый DoD каждой задачи:** код работает на воспроизводимой локальной конфигурации, есть тесты для существенной логики, ошибка логируется, документация/схема обновлена, отсутствуют скрытые зависимости от GPU и облака.

**Артефакты проверки:** писать в `benchmarks/reports/`, `tests/fixtures/`, при изменении интерфейсов — в `Workspace.md` или `docs/adr/`.

---

## F0 — Исходная инфраструктура и быстрые проверки

**Цель:** работающая локальная среда и ясная картина наличия/совместимости моделей. Gate **G0-env**.

### F0.01 — Инициализация репозитория [P0]
- [x] Создать `pyproject.toml`, `src/shsd/`, `tests/`, `configs/`, `scripts/`, `benchmarks/`.
- [x] Настроить `ruff`, `pytest`, type checking (например, `mypy` или `pyright`), единый Python ≥3.11.
- [x] Зафиксировать структуру модулей и разбиение на процессы.
- [x] Указать поддерживаемые OS/architecture и инструкции `CPU-only install`.
- **Depends:** нет.
- **DoD:** импорт `shsd`, минимальный CLI `shsd --help`, статические тесты и lint проходят.

- **Проверка:** Python 3.14.6; импорт `shsd` и установленный `shsd --help` успешны; `python -m pytest` — 3 passed; `python -m ruff check .` — all checks passed; `python -m mypy` — no issues found. F0.01 завершена.
### F0.02 — Локальные модели и версии [P0]
- [x] Проверить `google/embeddinggemma-2` через официальный multimodal Sentence Transformers API.
- [x] Проверить актуальный runtime `llama.cpp` для Qwen3-0.6B GGUF и качество русского в non-thinking режиме.
- [x] Найти рабочий GigaAM вариант через официальный репозиторий; ASR оставить выключенным по умолчанию.
- [x] Зафиксировать IDs, revisions, quantization, требования к лицензии, checksums в `models.lock.json`.
- [x] Сделать явную опцию `--offline` / `HF_HUB_OFFLINE=1` после скачивания.
- **Depends:** F0.01.
- **DoD:** модели воспроизводимо грузятся локально на CPU, результаты smoke test сохранены; при отсутствии весов выводится понятная ошибка, а не молчаливый download.
- **Проверка:** `benchmarks/reports/model_smoke.json` подтверждает offline CPU smoke на 4 threads: EmbeddingGemma 2 (revision `914f7f8`) дал конечные ненулевые L2-нормализованные 768d vectors для text/image/audio/video/joint и проверку cache reuse; Qwen3-0.6B Q8_0 / llama.cpp b11886 сгенерировал русскую фразу только из prompt facts; GigaAM v3 e2e CTC загрузился offline и выполнил inference (частичный transcript, без утверждения о точности). `models.lock.json` содержит revisions, quantization, licenses и SHA-256. Запуск `smoke_models.py` с пустым `--models-dir` вернул exit 2 и явную инструкцию вызвать downloader; `shsd analyze --offline` использует локальные веса.

### F0.03 — Замер базовой производительности [P0]
- [x] Зафиксировать сведения о CPU, RAM, ОС, числе потоков и ISA, доступных инструкциях AVX/ARM.
- [x] Замерить `EmbeddingGemma.encode_texts`, `encode_audio` для 3/5/10 сек, `encode_frame`, опциональный joint input.
- [x] Замерить Qwen cold start, prompt processing, tok/s при 64/128/256 output tokens.
- [x] Проверить изменение latency при 1/2/4 рабочих процессах и ограничении CPU threads.
- [x] Заполнить `benchmarks/reports/baseline_cpu.md` со средними, p50/p95, peak RAM, без «ожидаемых» чисел вместо фактических.
- **Depends:** F0.02.
- **DoD:** измерен один полный короткий круг audio→embedding + text→embedding + top-k + Qwen; оценён CPU bottleneck.
- **Проверка:** `benchmarks/reports/baseline_cpu.json` и `.md` получены командой `scripts/benchmark_cpu.py --offline --threads 1 2 4 --workers 1 2 4 --repeats 3`. Хост — Ryzen 9 9900X3D, 12 физических / 24 логических ядер, 95 909 MiB RAM, Windows 11, Python 3.14.6; ISA содержит AVX/AVX2 и AVX-512 варианты без AVX512_BF16. При 4 threads audio encode 5s — 274.6 ms p50 / 281.0 ms p95, video encode 8s — 12 837 ms / 13 350 ms, joint AV — 10 251 ms / 10 614 ms, top-k — 0.021 / 0.073 ms. 4 процесса дают 0.744 3s audio tasks/s при 10 548 MiB peak process-tree RSS. Qwen 256-token fresh process — 5 608 / 5 658 ms, generation — 55.7 / 57.1 tok/s. Главный measured bottleneck — vision/video inference; real-time не заявляется.

### F0.04 — Набор тестовых файлов [P0]
- [x] Подготовить 5–10 маленьких разрешённых/собственных тестов: музыка, речь, тишина, движение, смена сцены, аудио без видео и видео без аудио.
- [x] Добавить искусственный `fixtures/av_sync_20s.mp4` или генератор воспроизводимой синтетики.
- [x] Сохранить ожидаемые PTS интервалы, разметку **для ручного теста** и лицензии. Не называть это обучающим датасетом.
- **Depends:** F0.01.
- **DoD:** тесты не требуют сетевого доступа; крупные медиа исключены из Git либо хранятся через отдельный manifest.
- **Проверка:** `python scripts/generate_fixtures.py` создал 9 локальных файлов; `tests/fixtures/manifest.json` содержит SHA-256, PTS/time_base, интервалы и `must_not_claim`; общий размер 3 269 372 байта; fixture tests и PyAV demux проходят без сети.

**Выход фазы F0:** проверенные способы загрузки моделей, измерения базовых CPU-задержек, набор минимальных тестов.

---

## F1 — Ingest, синхронизация и 600-секундный ring

**Цель:** медиа-таймлайн без ML, пригодный для live. Gate **G0**.

### F1.01 — Media clock, PTS и epoch [P0]
- [x] Реализовать `stream_id`, `epoch`, преобразование `pts × time_base` в milliseconds без накопления float drift.
- [x] Обработать VFR, отсутствующий PTS, offset аудио и видео, скачки времени, reconnect, seek.
- [x] Определить интервал как `[start_ms, end_ms)`; создать `clock.py` с тестами округления.
- **Depends:** F0.01, F0.04.
- **DoD:** синтетические аудио/video события с разными time_base совмещаются с заданным допуском (например, ≤1 frame); seek переводит stream в новый epoch.
- **Проверка:** `tests/unit/test_clock.py` проверяет точное Fraction-округление, VFR, offset и AV alignment ≤40 мс, fallback для отсутствующего PTS, скачок/откат времени, seek/reconnect; общий запуск — 60 тестов.

### F1.02 — Demux MP4/MKV и audio/video-only [P0]
- [x] Создать streaming PyAV/FFmpeg demux-reader, не загружать весь файл в RAM.
- [x] Разделить вход audio/video, сохранить source PTS/time_base, start offset, codec info.
- [x] Добавить graceful EOF и controlled stop.
- **Depends:** F1.01.
- **DoD:** 5+ фикстур демультиплексируются без потери порядка; отсутствие модальности представлено `unavailable`.
- **Проверка:** PyAV 19.0.1 потоково прочитал все 9 WAV/MP4/MKV фикстур; packet index, PTS, time_base, offset и audio/video-only unavailable проверяются в `tests/unit/test_demux.py`.

### F1.03 — Bounded rolling media ring [P0]
- [x] Реализовать window 600s по timestamp, а не по количеству кадров/буферов.
- [x] Добавить refcount/leases для chunk, сохранение важных ресурсов во время активной обработки.
- [x] Настроить bounded spill-to-disk и явное событие `dropped` при отказе.
- [x] Обработать удаление oldest chunk без повреждения таймлайна.
- **Depends:** F1.02.
- **DoD:** soak-тест минимум 30 минут source-time без неограниченного RAM growth; leases и удаление работают.
- **Проверка:** тест прогнал 1 800 секунд source-time с 1-секундными chunks при memory cap 1 000 000 байт; `tracemalloc` peak ограничен 8 MiB; проверены 600-секундное окно, лимит числа chunks, spill/lease/release, удаление и явный `dropped`; общий запуск — 60 тестов.

### F1.04 — Replay control [P1]
- [x] Режим `--simulate-realtime`: подавать локальный файл по media clock.
- [x] Режим `--fast`: обрабатывать offline максимально быстро без имитации live.
- [x] Pause/resume/seek с понятными epoch и recalc policies.
- **Depends:** F1.02, F1.03.
- **DoD:** в тесте pause не теряет положение, seek не пишет старые revision в новый epoch.
- **Проверка:** `ReplayController` покрывает pause/resume/stop/seek и вызывает `on_epoch_started`; callback напрямую подключается к `EventStore.begin_epoch`. Установленный `shsd replay` прошёл fast-прогон 20-секундного MKV (409 пакетов) и realtime-прогон 3-секундного MP4. Интеграционный тест подтверждает, что после seek `EventStore` отклоняет позднюю запись из прошлого epoch; compare-and-swap ревизий также проверен в `tests/unit/test_memory.py`.

**Выход фазы F1:** устойчивый IO pipeline + ring buffer без инференса.

---

## F2 — Semantic perception и L0/L1 (первый end-to-end смысловой срез)

**Цель:** реальное аудио/видео → эмбеддинги → топ гипотез с доказательствами. Gate **G1 + G2**.

### F2.01 — Cheap detectors [P1]
- [x] Реализовать RMS/loudness, VAD (лёгкий), onset/novelty для аудио.
- [x] Реализовать downscaled frame diff/scene-cut для видео.
- [x] У каждого измерения должны быть interval, subtype, quality и версия метода.
- **Depends:** F1.02.
- **DoD:** изменения и отсутствие активности обнаруживаются на контролируемых синтетических примерах.
- **Проверка:** `tests/unit/test_detectors.py` проверяет цифровую тишину, активный тон/onset, audio quality и scene cut с корректным интервалом; observations содержат subtype, quality и method_version. RGB-метрика с порогом 0.08 находит три перехода 1.9–2.0, 3.9–4.0 и 5.9–6.0 с в синтетическом 8-секундном клипе. Полный набор — 107 passed.

### F2.02 — Embedding provider & cache [P0]
- [x] Реализовать `encode_audio`, `encode_frame`, `encode_texts`, как определено в `Workspace.md`.
- [x] Обеспечить CPU-only device, отключение отсутствующих модальностей при загрузке.
- [x] Кэшировать нормализованные vectors в дисковом хранилище с model/preproc fingerprints.
- [x] Не вычислять текстовые embeddings заново на каждом media chunk.
- [x] Замерить скорость audio-only, video-only и совместной загрузки.
- **Depends:** F0.02, F1.02.
- **DoD:** 768d векторы валидны/ненулевые, воспроизводимы; cache hit не вызывает модель; тест input audio/frame и quality check.
- **Проверка:** `model_smoke.json` подтвердил конечные ненулевые 768d L2 vectors и cache reuse. `demo_av_sync_20s.jsonl` содержит 8 холодных multimodal embeddings; `video_only_smoke.jsonl` подтверждает video-only загрузку без аудиокодера (624 вместо 1376 весов) и 0 ms audio stage. Baseline audio/frame/joint latency находится в `baseline_cpu.md`.

### F2.03 — Гипотезы v0 [P0]
- [x] Создать `hypotheses/music.yaml`, `sound.yaml`, `visual.yaml`, `av.yaml`.
- [x] На уровне музыкальных осей предусмотреть отрицательные пары и unknown.
- [x] Сгенерировать/написать компактные полные предложения для broad и detailed категории; переводы на русский сохранять как отображение, если scoring идёт на EN.
- [x] Версионировать файл кандидатов вместе с cached text vectors.
- **Depends:** F2.02.
- **DoD:** минимум 10 осей, по 2+ конкурирующих кандидата для основных осей, нет «невозможно определить» как принудительно позитивной метки.
- **Проверка:** `load_profiles()` загрузил 4 профиля, 16 осей и 33 кандидата; `tests/unit/test_semantic.py` проверяет конкурирующие гипотезы, неэмбеддируемый `unknown`, fingerprint и ревизию модели.

### F2.04 — Semantic matcher [P0]
- [x] Cosine similarity на совместимом L2-normalized пространстве.
- [x] `top_k` per axis, margin vs competitor, threshold и `accepted/uncertain/rejected`.
- [x] Не интерпретировать cosine как процент уверенности.
- [x] Если ни один кандидат не проходит gate — `unknown`/`abstain`.
- [x] Для non-exclusive осей оценивать каждый кандидат независимо от top-k; сохранять все individually-supported claims с evidence и требовать temporal persistence для отдельного L1 event.
- **Depends:** F2.02, F2.03.
- **DoD:** нормальные/контрастные аудио фрагменты дают интерпретируемый ранжированный список; uncertain видно в API.
- **Проверка:** `tests/unit/test_semantic.py` покрывает accepted, below-threshold abstain, малую margin как `uncertain` и несколько независимых supports вне global top-k; `tests/unit/test_memory.py` и `tests/unit/test_analyze.py` подтверждают раздельную temporal persistence и публикацию нескольких инструментальных events с evidence. JSONL сохраняет raw cosine и `similarity_is_probability=false`.

### F2.05 — Temporal L1 events [P0]
- [x] Объединить соседние window match results через hysteresis, persistence и semantic state.
- [x] Детектировать `music_started/stopped/changed`, `scene_changed`, `speech_detected`, `sound_effect`, `unknown`.
- [x] Сохранять `evidence_refs`, `window_ids`, интервалы и model fingerprint.
- [x] Продлевать stable events вместо генерации повторного «продолжается музыка».
- **Depends:** F2.01, F2.04.
- **DoD:** изменения порождают новые события, стабильная сцена объединяется, историю можно воспроизвести из event log.
- **Проверка:** `TemporalEventReducer` требует два последовательных окна по умолчанию, продлевает прежний `event_id` новой revision, создаёт отдельное событие после устойчивой смены кандидата и игнорирует дубли окна. Scene-cut signal создаёт L0 event; SQLite WAL хранит append-only revisions с expected-revision CAS и epoch high-water. `tests/unit/test_memory.py` проверяет смену, стабильное продление, seek epoch, scene cut и отказ от stale writes; полный набор — 107 passed.

### F2.06 — Первый вертикальный Demo [P0]
- [x] Команда `shsd analyze test.mp4 --levels L0,L1 --cpu-only` (после реализации CLI) выводит JSONL событий.
- [x] Показывает модальности, таймкоды, top candidates, abstain, версии.
- [x] Предусмотреть metric `end_to_end_elapsed`, per-worker stage timing.
- **Depends:** F1.02, F2.02–F2.05.
- **DoD:** на реальном файле появляется evidence-grounded L1 без вызова Qwen и без обучения.
- **Проверка:** cold run `av_sync_20s.mp4` записан в `benchmarks/reports/demo_av_sync_20s.jsonl`: 8/8 embeddings имеют `cache_hit=false`, 29.53 s end-to-end, 32 semantic matches, 24 detailed music matches пропущены при uncertain presence, сохранены 3 scene cuts; Qwen не запускался.

**Выход фазы F2:** рабочий inference path, годный для сравнения с ручными наблюдениями. **STOP/GO:** если EmbeddingGemma не различает желаемые музыкальные детали на коротких пробах, не заявлять о детализации; добавить независимые DSP признаки или ограничить claims.

---

## F3 — L2: временное уточнение, музыка, опциональный ASR

**Цель:** изменения музыки и действий, сохранение uncertainty, независимые речевые подсказки. Gate **G2+**.

### F3.01 — Temporal state & delta [P1]
- [x] Построить `active_music`, `active_scene`, `active_speakers`, `last_meaningful_change`.
- [x] Сохранить previous state и hysteresis до публикации нового состояния.
- [x] Рассчитывать novelty для сопоставимых интервалов; обрабатывать пересекающиеся окна и неоднозначные границы.
- **Depends:** F2.05.
- **DoD:** перестановка последовательности тестовых событий меняет итоговый event sequence; дублирование окон не даёт удвоения смысла.
- **Проверка:** `TemporalStateReducer` сохраняет snapshots/delta только из accepted claims, удерживает неоднозначные/пересекающиеся переходы и дедуплицирует revision/window IDs. `tests/unit/test_memory.py` покрывает epoch reset, reorder, hysteresis, overlap и novelty.

### F3.02 — Многоступенчатые музыкальные гипотезы [P1]
- [x] Сначала определить наличие/характер музыки, затем проверять family инструментов, ударные, бас, вокал, изменения.
- [x] Включить «невозможно различить синтезатор/бас-гитару» как корректный результат.
- [x] Проверить относительные свойства (прибавился/исчез/усилился) сравнением соседних окон + onset/RMS.
- [x] При недостатке evidence описывать изменения громкости или спектра, но не приписывать конкретный инструмент.
- **Depends:** F3.01, F2.04.
- **DoD:** минимум 4 тестовых кейса change/no-change; detailed claims привязаны к источникам.
- **Проверка:** `compare_audio_windows()` измеряет соседние неперекрывающиеся окна по RMS/loudness/onset/activity/spectral centroid; при overlap не выдаёт delta. 4 теста `test_novelty.py` покрывают no-change, уровень/onset, спектр при равной энергии и overlap; detail claims открываются только после accepted `music_present` и получают `evidence_refs`.

### F3.03 — Контролируемый iterative prompting [P2]
- [x] По явному `--iterative-axis` Qwen предлагает до шести кандидатов только для выбранной оси после baseline top-k.
- [x] Ограничить одной попыткой на axis и бюджетом 15 секунд; при timeout/ошибке/перерасходе остаётся baseline.
- [x] Новые строки проверяет EmbeddingGemma по обычным порогам; Qwen сам не подтверждает свои предложения, похожие на существующие vectors (>0.92 cosine) отбрасываются, baseline accepted claim нельзя заменить.
- [x] Add `hypothesis_iteration` comparison rows and `scripts/evaluate_iterative_hypotheses.py` for manually labeled A/B accuracy, coverage, and latency.
- [x] Expand the exploratory natural set to 40 windows with group conversation, speech over market music/noise, choral singing, and rainy urban ambience; retain licenses, source offsets, and SHA-256, then rerun the complete CPU A/B.
- [x] Prepare a blinded listening review pack for all 40 windows with shuffled IDs, local WAV clips, a separate answer key, and an import path for independently reviewed labels. Pack: `benchmarks/review/iterative_speech_presence_natural/`; generator: `scripts/build_audio_review_pack.py`; label importer: `scripts/import_audio_review_labels.py`. Build smoke verified 40 mono 16 kHz / 5 s WAVs against clip SHA-256 values and confirmed the player omits source names and expected labels. Importer smoke with synthetic input produced 39 binary interval labels and excluded one `uncertain`; Ruff and `py_compile` pass.
- [ ] Run A/B on representative hand-labeled audio and leave the feature disabled if dynamic candidates do not improve quality.
- **A/B evidence:** `benchmarks/reports/iterative_speech_presence/` records the earlier six-fixture test. `benchmarks/reports/iterative_speech_presence_natural/` now records an offline CPU A/B on 40 five-second windows from 11 independent recordings: 20 speech-positive (14 archival, 3 group-discussion, 3 market-with-background-music) and 20 negative (10 piano, 3 choir, 4 weather/wind, 3 urban-rain). All 40 labels matched. Baseline and iterative modes were identical: 1/40 accepted-correct (2.5% coverage) and 24/40 correct top-ranked candidates (60.0%; speech 18/20, music including choir 2/13, environmental 4/7). Qwen returned no candidates in three per-stream attempts (9.508 s aggregate). Keep the feature opt-in. The sample remains exploratory: the conversational and mixed-noise coverage is one short recording each, and new intervals were labeled from source descriptions rather than independently reviewed by listening; varied languages/microphones and broader music/noise conditions remain uncovered.
- **Depends:** F2.04, F4.01.
- **Verification:** unit tests cover JSON parsing, candidate limits/deduplication, independent embedding support, baseline fallback, the one-attempt limit, and A/B scoring. A full local analyze/A/B run uses Sentence Transformers 6.2.0 / Transformers 5.20.2 / Hub 1.33.0. Qwen returned malformed/repeated JSON in an earlier run and the parser rejected the suggestions; baseline and iterative results matched. Raw timelines and provisional labels are in `benchmarks/reports/iterative_speech_presence_natural/`. A blinded 40-clip player plus CSV-to-evaluator import path is ready at `benchmarks/review/iterative_speech_presence_natural/`; the current source-description labels are still not independent listening labels.
- **DoD:** dynamic candidates did not improve baseline on the 40 evaluation-only natural windows, so the feature stays opt-in. Reliable real-source quality remains unestablished; representative independent labels still need listening review across speakers, languages, microphones, and speech-over-noise.

### F3.04 - GigaAM optional ASR lane [P2]
- [x] Integrate the local GigaAM-v3-e2e-CTC CPU checkpoint with SHA-256 checks for config, model code, weights, and tokenizer; load only from the local model directory.
- [x] Split audio into bounded windows up to 20 seconds and emit `speech_segment` rows with `start_ms/end_ms`, `language`, media source, model revision, and partial-to-final revisions. Timestamps cover the whole audio window; word timing is not claimed.
- [x] Enable speech independently through CLI `--speech`, API `speech_enabled`, and the UI switch; default remains off. Bounded input/result queues report `dropped` on backpressure, while ASR errors remain speech records and do not stop audio/video analysis.
- [x] Do not claim diarization; `ru` comes from the selected Russian GigaAM-v3 model family.
- [x] Persist partial/final revisions in SQLite; expose `/v1/streams/{id}/speech`, a Speech lane, and JSON/JSONL/Markdown export.
- **Depends:** F0.02, F1.02.
- **DoD:** ASR toggles independently. A fake-embedding comparison confirmed identical audio observations and L1 decisions with ASR on/off and with an ASR failure. The local model completed real CPU inference on a 5-second synthetic Russian fixture; this is a smoke test, not a quality evaluation.
- **Verification:** `tests/unit/test_asr_worker.py`, `tests/unit/test_analyze.py`, `tests/unit/test_memory.py`, `tests/unit/test_api.py`; local GigaAM inference completed with locked artifact checksums under Transformers 5.20.2. The actual analyzer ran EmbeddingGemma + GigaAM concurrently on the 5-second fixture and emitted partial/final speech rows with zero ASR errors/drops; see `benchmarks/reports/iterative_speech_presence/asr_embedding_smoke.jsonl`. This remains a model smoke, not a transcript-quality evaluation.

### F3.05 — Cross-modal relation validator [P2]
- [x] Сопоставлять video scene cut с ближайшим audio onset в PTS tolerance 250 ms; event evidence включает обе наблюдаемые модальности и method versions.
- [x] Текст события говорит только о временном совпадении; причинность не выводится из синхронности.
- [x] При отсутствии audio/video вернуть `unavailable`; bounded signal retention сообщает `truncated` и счётчик отброшенных наблюдений.
- **Depends:** F3.01, F2.01.
- **DoD:** в синтетическом тесте намеренно сдвинутая дорожка не считается синхронной.
- **Проверка:** `tests/unit/test_relations.py` проверяет точное совпадение в допуске, сдвиг вне tolerance, обе evidence refs, отсутствие causal claim, unavailable modality и bounded truncation.

**Выход фазы F3:** более полезный для человека L2, но всё ещё без генеративной AV-LLM.

---

## F4 — L3: русский Narrator и Progressive Commit

**Цель:** подробный связный текст без неподтверждённых сведений. Gate **G3 + G4**.

### F4.01 — Frozen Qwen narrator [P0]
- [x] Локальный интерфейс к `llama.cpp`/Qwen3-0.6B в non-thinking mode.
- [x] Ограниченные `max_tokens`, timeout и входные chunks.
- [x] Вход только `accepted claims`, ASR цитаты с качеством, delta/state и IDs.
- [x] Создать versioned русский prompt template с явным запретом на неподтверждённые детали.
- **Depends:** F0.02, F2.05.
- **DoD:** одна L2 группа событий превращается в читаемое русское описание и schema-valid JSON.
- **Проверка:** `scripts/smoke_narrator.py --threads 4 --max-tokens 96` запущен offline на Qwen3-0.6B Q8_0 revision `13ac066`; вывод — «Слышна музыка.», JSON Schema валиден, claim/event revision и time range совпадают с входом. Измеренная latency одного запуска — 1774.981 ms. Prompt `narrator-ru-v1`, timeout 45 s, chunk cap 4096 символов.

### F4.02 — Контроль «новых фактов» [P0]
- [x] JSON schema/typed model ответа: `caption_ru`, `used_claim_ids`, `time_range`, `warnings`.
- [x] Валидировать `used_claim_ids` против событий и их revisions.
- [x] Минимизировать риск текстовой галлюцинации: schema + ограничения + независимый deterministic fallback.
- [x] Если обнаружены неподдерживаемые claims или malformed JSON — fallback вместо «автоисправления» выдуманной детали.
- **Depends:** F4.01.
- **DoD:** adversarial тест (нет инструмента в claims) не допускает его упоминания в committed caption; ошибочный JSON не портит событие.
- **Проверка:** `narration_v1.schema.json` валидирует запись smoke report; `NarrationRequest` связывает каждый claim с event/revision, а результат сохраняет эти revisions. `tests/unit/test_narrator.py` заставляет fallback на «гитара» без такого слова в evidence, на смену отрицания, пустой/non-Russian ответ и timeout; fallback повторяет только исходные claims/цитаты. Ограничитель проверяет словарь/отрицания консервативно и не заявляет полного semantic entailment.

### F4.03 — Async jobs L1/L2/L3 [P0]
- [x] Очереди отдельных классов задач, bounded capacity, dedup по `(stream,epoch,event,revision,level)`.
- [x] Результаты писать через единый logical event writer с expected revision.
- [x] Задачи L1 не ждут L3; L3 умеет объединять несколько стабильных событий.
- [x] Ввод не ждёт ни одного ML worker.
- **Depends:** F2.05, F4.01.
- **DoD:** искусственное замедление L3 не задерживает C и L1; out-of-order response не затирает новое описание.
- **Проверка:** `tests/unit/test_scheduler.py` удерживает L3 и подтверждает завершение L1, проверяет batching двух стабильных событий, duplicate/full outcomes, отмену queued work и CAS rejection позднего L1 после записи L2. `submit()` использует `put_nowait()`; полный набор — 107 passed.

### F4.04 — Watermarks / Progressive Commit [P0]
- [x] Вычислять `C`, `E`, `D[level]`, `R[level]` по contiguous interval coverage.
- [x] Различать `done`, `pending`, `gap`, `unavailable`, `dropped`.
- [x] Revision/version semantics и event merge/split.
- [x] API отдаёт отставание по уровням и по модальностям.
- **Depends:** F4.03, F1.01.
- **DoD:** property tests на holes, late updates, seek, retry, overlap и cancellation.
- **Проверка:** `tests/unit/test_watermarks.py` покрывает межмодальный минимум C/E, pending holes, terminal gap/unavailable/dropped, retry revisions, interval split/merge и stale epoch. `snapshot()` отдаёт `C/E/D/R`, per-level lag, per-modality cursors и issues. Дополнительная live-регрессия нашла и исправила блокирующий прогресс R[L1]: leading PTS holes теперь имеют явный `gap`, аудио E закрывает начальный PTS offset, а semantic watermark не расширяет source horizon. Loopback 2x/5x: `benchmarks/reports/live_rtsp_priority_progressive_commit_60s_20261026.md`; полный набор — 166 passed.

### F4.05 — Первый полный PoC [P0]
- [x] Запуск `file.mp4 → L0/L1/L2/L3 → Russian captions JSONL`; при запросе L2/L3 включаются необходимые нижние семантические уровни.
- [x] На протяжении обработки показывать cursor positions и оставшийся backlog в watermark JSONL и stderr CLI.
- [x] Провести ручную структурную проверку восьми локальных synthetic fixtures: AV sync, синтетическая музыка/тон/тишина/речь, scene cuts, движение и статичное видео.
- **Depends:** F4.01–F4.04, F3.01.
- **DoD:** выводы честно содержат unknown/uncertain, поддерживают append-only revisions, выполняются на CPU без обучения.
- **Проверка:** `benchmarks/reports/poc_manual_review.md` фиксирует результаты восьми прогонов; отдельные JSONL содержат промежуточные и итоговые watermarks, L0/L1/L2 revisions и captions. Все captions проходят JSON Schema и ссылаются на существующие L2 revisions. В музыке и речи пороги устойчивости не пройдены — caption не создан; пропуски и unavailable-модальности видимы. Полный набор — 107 passed, Ruff и mypy проходят. Fixtures синтетические; распознавание реальных инструментов, шумов, действий и речи этой проверкой не подтверждено.

**Выход фазы F4:** минимально работоспособный мультимодальный таймлайн с асинхронным прогрессивным описанием.

---

## F5 — API, UI, replay и удобство контроля

**Цель:** визуально наблюдать, как курсоры и уровни догоняют поток. Gate **G5**.

### F5.01 — REST + WebSocket server [P1]
- [x] Реализовать локальный file API для `/v1/streams`, `/timeline`, `/watermarks`, `/metrics`, `/refine`, `/events/{event_id}`.
- [x] WebSocket публикует create/revise/commit/error/gap; клиент reconnect получает retained backlog или явный backfill gap.
- [x] До публикации фильтровать дубликаты и stale revisions; закрепить контрактные и reconnect проверки.
- **Depends:** F4.04.
- **DoD:** API contract tests + reconnect integration test.
- **Проверка:** `tests/unit/test_api.py` проверяет create/status/timeline/history/watermarks/metrics, L2 refine CAS revision, WebSocket replay после disconnect, ограниченный journal с `gap_detected`, поведение stale/duplicate revisions и stream errors. `shsd serve` поднимает API на localhost; `pip install -e ".[api]"` устанавливает сервер. Текущий API ограничен локальными файлами и не восстанавливает WebSocket journal после перезапуска; live URL и controls оставлены открытыми в спецификации.

### F5.02 — UI: 10-минутный rolling timeline [P1]
- [x] Дорожки Video, Music, Sound, Speech, L1, L2, L3.
- [x] Отрисовать C и R для выбранного уровня; опционально E/D.
- [x] На click показывать caption, evidence, статус, revision и историю версий.
- [x] Показывать missing/unavailable/dropped отдельным паттерном и текстом.
- [x] Ручное `refine interval` и переключение L1/L2/L3.
- **Depends:** F5.01.
- **Проверка:** `/ui/` и статические ресурсы проверяются API-тестом; JS проходит `node --check`. Chrome/Playwright подтвердил Speech segment partial→final, переключение темы, E и уровня, ширину без горизонтального overflow при 280/320/414/768/1280 px, без ошибок JS. На реальном `video_motion_8s.mp4` при выбранном L3 браузер зафиксировал 22 изменения DOM с C ahead of R[L3]; see `benchmarks/reports/ui_f502_browser_acceptance.json`. CSS lint дизайн-токенов в проекте отсутствует.
- **DoD:** подтверждено в живом браузере: C продвинулся до 5 s при R[L3]=0, затем оба дошли до 8 s после завершения обработки.

### F5.03 — Сохранение и экспорт [P2]
- [x] JSON/JSONL экспорты событий/revisions и Markdown-транскрипт по времени.
- [x] Пользователь может запросить связный текст по сохранённым captions без повторного мультимодального анализа.
- [x] Экспорт предупреждений о пропусках и uncertain claims.
- **Depends:** F4.02, F5.01.
- **Проверка:** `tests/unit/test_memory.py` проверяет повторное открытие caption/metadata store; `tests/unit/test_api.py` проверяет JSON/JSONL/Markdown, предупреждения, revisions и replay REST после рестарта manager без вызова inference.
- **DoD:** после рестарта stream replay читается из событий и captions без исходного ML-инференса.

---

## F6 — CPU-производительность, деградация и финальный эксперимент

**Цель:** получить реальные числа и инженерное решение о целевой скорости. Gate **G6**.

### F6.01 — Scheduler с backpressure [P0]
- [x] Семантический scheduler сохраняет L1 при давлении; post-analysis refine очередь ставит L2 выше L3.
- [x] Bounded L1/L2/L3 очереди, отмена queued jobs, bounded API refine queue и merge смежных ожидающих L3 интервалов.
- [x] `RuntimeLoadController` переключает `normal / degraded / critical` по queue occupancy, lag, CPU и RSS; эскалация немедленная, recovery с hysteresis.
- [x] Переполнение имеет явный исход: scheduler возвращает `FULL`/`PRESSURE` и вызывает callback с причиной, API отвечает `429`; файл replay ring уже выдаёт `dropped` с причиной и имеет bounded spill.
- [x] Первый file-ingest срез `shsd replay`: сжатые PyAV-пакеты проходят через bounded `MediaRing`; C watermark учитывает обе модальности и явные drop spans, optional `psutil` замеряет host CPU/RSS, buffer occupancy и realtime lag передаются в `RuntimeLoadController`. Приёмочный replay `av_sync_20s.mp4`: 1 139 пакетов, C=20 000 мс, 0 потерь.
- [x] `analyze_media()` передаёт L2 event refinements в `AsyncLevelScheduler` с bounded queue и измеренным host CPU/RSS; отклонённые задания оставляют `scheduler_degradation` и `runtime_backpressure` coverage. Нормальный video-only прогон завершил L2; с memory limit 1 byte scheduler отклонил 9 L2 заданий, сохранив L1.
- [x] Анализатор теперь принимает compressed audio/video packets через bounded `MediaRing`, повторно читает их через leases и декодирует из сохранённых bytes; capture drops отмечаются в C, audio discontinuities разделяют окна. A/V smoke: 1 139 пакетов (939 audio, 200 video), C/E=20 000 мс, 0 drops и 0 capture issues.
- [x] Ограниченный producer/consumer path перекрывает audio decode/windowing с audio L0/L1 обработкой; для A/V video capture/decode producer запускается до audio embeddings. Очереди ограничивают опережение и записывают peak depth/block time. A/V smoke после запуска producer: 1 139 пакетов, C/E=20 000 мс, 0 drops; video queue 8/8, один backpressure stall 298 мс.
- [ ] Complete the sustained 2x/5x live acceptance and physical-camera validation. URL/live L2/L3 now execute online with distinct bounded queues and the shared `RuntimeLoadController.admit()` contract; file-mode L2 refinement remains post-analysis.
  - [x] Two-minute four-thread `adaptive` vs `standard` live RTSP comparison: adaptive reduced embedding jobs but did not improve RTF; 2x R/L1 issue coverage rose from 0.3% to 64.7%, and 5x rose from 81.7% to 89.9% with 65.1 s peak L1 lag. Keep adaptive opt-in pending independent labels; no 5x profile meets sustained real-time acceptance. Physical-camera validation remains open. See `benchmarks/reports/live_rtsp_adaptive_2m_threads4_20261026.md`.
  - [x] P0 capture/drop coverage wins timestamp ties; shared `admit()` applies P1 L0/embeddings, P2 L1, P3 L2/ASR, and P4 L3 across worker lanes. P3 ASR uses a bounded deferred buffer with explicit dropped coverage if pressure persists; load state keeps the highest queue pressure and lag/CPU/RSS signals.
  - [x] Full unit suite: 153 passed; ruff, worker mypy, and py_compile passed. Post-admission 20 s A/V CLI smoke reached C/E/R(L1)/R(L2)=20,000 ms, 31 L1 and 14 L2 events, 0 scheduler rejects, and normal final load.
  - [x] One-cycle concurrent file smoke after shared admission: 2 streams passed in 16.3 s (aggregate RTF 0.408, peak RSS 4,667 MiB); 5 streams passed in 18.5 s (RTF 0.1855, peak RSS 11,677 MiB). Both scales reached C/E/R(L1)/R(L2)=20,000 ms per stream with 36 matches and zero coverage misses, ingest/prefetch drops, or scheduler rejects. This is warm-cache file concurrency evidence, not live-source validation; raw timelines are in `benchmarks/reports/shared_priority_scale_smoke_20261026/`.
  - [x] Проверено DELETE во время stalled loopback RTSP read: 9 ms на ответ API, 418.9 ms до terminal `stopped`, без ошибки; см. `benchmarks/reports/rtsp_stalled_read_stop_smoke.md`.
   - [x] One-minute synthetic RTSP runs reached terminal shutdown and kept RSS below 2.35 GiB. With the original one-thread setting, 5x final L1 lag was 15.2-17.4 s and stop wait 48.744 s. A controlled four-thread rerun increased embedding jobs from 45 to 64, reduced prefetch drops 4,371 to 2,723 and stop wait to 15.030 s, and left 0-3.470 s final L1 lag; API p95 was 284 ms, max 508 ms, and peak RSS 2.347 GiB. This is post-stop drain on synthetic loopback, not proof of continuous realtime processing. See `benchmarks/reports/live_rtsp_priority_threads4_60s_20261026.md`.
  - [x] Watermark/analysis metadata checkpoints use one coalescing background drain per manager; final session state is persisted before analysis completion. A blocked-writer unit test confirms publication returns without waiting and that 100 updates persist the latest snapshot in at most two writes. `tests/unit/test_api.py`; 165 unit tests, Ruff, and Mypy pass.
   - [x] The live RTSP benchmark accepts `--threads`; warmed 15-window inference p50 fell from 581.8 ms (1 thread) to 263.6 ms (4), and 12-window vectors matched with cosine >=0.999999999998. The 60 s 2x/5x four-thread report records improved post-stop drain with the current remaining live/camera gaps: `benchmarks/reports/live_rtsp_priority_threads4_60s_20261026.md`.
  - [x] 60-second live thread sweep at 4/8/12 threads: every synthetic 2x/5x scenario reached capture-ready and terminal stop, but none met the 5x real-time target (RTF median 1.108–1.186; peak observed L1 lag 41.3–51.9 s; final R/L1 gap/skip spans 56.8%–85.6% of captured media). Eight threads had fewer final L1 issue spans, while twelve had the lowest RTF; both had more prefetch drops or scheduler pressure than four threads. Keep four threads as the default. Physical-camera validation remains pending. See `benchmarks/reports/live_rtsp_thread_sweep_60s_20261026.md` and the raw 8-thread run in `benchmarks/reports/live_rtsp_shared_dispatch_threads8_60s_20261026/report.json`.
  - [x] 120-second live soak on the four-thread / 5-second default, four-thread / 10-second window, and twelve-thread / 5-second controls. At 2x, the default held peak L1 lag to 5.9 s and 0.3% final R/L1 issue spans; both sources ended in normal load with 2.32 GiB peak RSS. At 5x, default L1 lag rose from 6.1 to 55.1 s median across the run's quarters; four of five sources ended in critical queue pressure, with 2.35 GiB peak RSS under the 4 GiB limit. Twelve threads reduced the final-quarter median to 39.8 s but left 89.6% R/L1 issue spans, while the 10-second window left 85.9% and reached 64.3 s peak lag. No 5x setting is accepted as sustainable realtime. See `benchmarks/reports/live_rtsp_soak_2m_20261026.md` and its raw JSON files; physical-camera acceptance remains open.
  - [x] API classifies RTSP open/read/EOF failures and retries up to five times with exponential backoff capped at 8 s. An interrupted active analysis resumes in a new epoch, emits `stream.reconnecting`, ignores stale callbacks from the prior epoch, and stops promptly when DELETE arrives during the retry wait. Ordinary model/runtime failures are not retried. Unit evidence: `tests/unit/test_api.py`, `tests/unit/test_demux.py`.
  - [x] Loopback publisher stop/restart completed across epoch 0 → 1; the API resumed capture and later reached `stopped`. Raw evidence: `benchmarks/reports/rtsp_reconnect_smoke_20261026.md` and `benchmarks/reports/rtsp_reconnect_smoke_20261026/report.json`.
  - [x] Исправлен прогрессивный C/E watermark для отсутствующих дорожек при неизвестной длительности live URL; video-only RTSP снапшоты двигают общий C вместе с video cursor. Проверка находится в том же smoke report.
  - [x] Добавлена неблокирующая выборка нагрузки во время media interleave и drained-state sample перед L2 admission; 20 s A/V smoke сохранил 14 L2 events и ноль scheduler rejects. См. `benchmarks/reports/runtime_load_sampling_smoke.md`.
  - [x] В обычном режиме L1 scoring/reducer и scene-cut сигналы выполняются в отдельной bounded serial lane; scene-cut ставится после всех более ранних embedding jobs. SQLite записи из worker сериализуются общим lock.
  - [x] Проверен 20 s A/V → L0/L1/L2: C/E/R(L1)/R(L2)=20,000 ms, 36 L1 window matches, 31 L1 events, 14 L2 events, max L1 outstanding 2/4, 0 L1 failures и 0 scheduler rejects; полная unit suite: 148 passed. См. `benchmarks/reports/l1_worker_scheduler_smoke.md`.
  - **2026-10-26 online L2/L3:** URL/live mode commits L1 after the configured stability gap, sends L2 event revisions through a bounded worker, then queues eligible accepted claims for Qwen L3. Coverage barriers advance live R watermarks after prior work completes; event writes retain CAS revisions. `benchmarks/reports/live_qwen_online_smoke_20261026.md`: on 35 s of real-time RTSP publishing, 3 L2 events and 2 Qwen captions arrived before stop; R[L2]/R[L3] reached 5.11 s, first caption arrived at 25.9 s, source-event lag was 16.85–16.88 s, and post-stop drain was 0.66 s. Captions remained generic scene-cut descriptions; this proves online execution, not realtime throughput or useful music narration. Physical-camera and sustained 2x/5x acceptance remain open.
  - **Progress:** `analyze_media()` now merges bounded audio/video prefetch by monotonic work-ready timestamp through `iter_merge_by_key()` (one lookahead per source), then runs embedding/L1 in shared work-ready order. Evidence: `benchmarks/reports/analyzer_shared_interleave_smoke.md`; the 20 s A/V run captured 1,139 packets, reached C/E/R=20,000 ms, recorded 0 drops and 0 scheduler backpressure, and completed 14 L2 state events. Audio-only and video-only paths also passed. This earlier smoke verified readiness arbitration; the later shared P0-P4 admission contract is recorded below. Sustained live priority and 2x/5x latency remain open; RTSP reconnect is covered by the later API smoke.
  - **Progress:** `iter_bounded_prefetch()` exposes `block`, `drop_newest`, and `drop_oldest`; nonblocking overflow reports each discarded item through telemetry and an optional callback. `analyze_media()` connects the policies to its bounded decoder/window queues and preserves coverage; file analysis remains `block` by default. URL-based network ingest was added later in F6.01; physical-camera behavior remains open; API RTSP reconnect is covered by the later smoke.
  - **Progress:** the shared media admission heap now prioritizes capture/drop coverage over model work when readiness times tie, validates each input stream's monotonic work-ready keys, and reports capacity/peak/admitted/dispatched counts. The refreshed 20 s A/V smoke held at 2/2 pending items, dispatched 1,164 items, reached C/E/R=20,000 ms, and recorded 0 drops/backpressure. At that stage priority was only a tie-break; current embedding/L1/ASR/L2/L3 admission is shared, while the queues remain distinct.
  - **Progress:** `shsd analyze --prefetch-capacity 1 --prefetch-overflow-policy drop_oldest` exercised the real A/V producer/consumer path. Evidence: `benchmarks/reports/analyzer_prefetch_drop_smoke.md` and `.jsonl`; queues stayed at 1/1, reported 127 audio and 215 video dropped queue items without blocking, and recorded three dropped video embedding spans (5–5.001 s, 10–10.001 s, 15–15.001 s). C/E/R reached 20 s with those losses explicit; this is a local-file pressure run, not a live-stream or 2x/5x soak.
  - **Progress:** Added `scripts/benchmark_fullstack.py` for parallel CLI A/V runs, with cycle or wall-duration mode and JSON/Markdown output. The one-cycle scale smoke `benchmarks/reports/fullstack_av_scale_smoke.md` passed at 2x and 5x: 40/100 aggregate media-seconds, zero dropped/failed coverage, and 4.6/11.4 GiB peak combined process-tree RSS. The follow-up 1-minute run repeated the 20 s fixture for 4 cycles per scale: 2x finished 160 media-seconds in 69.9 s (per-stream RTF p50/p95 0.865/0.882), and 5x finished 400 media-seconds in 79.4 s (0.985/0.994). Both had zero ingest/prefetch drops and zero dropped/failed coverage; mean process use was 1.91/4.74 cores and peak aggregate process-tree RSS was 4.6/11.4 GiB. L1/L2 source-time watermark lag p50/p95 was 10/20 s: the finite-file analyzer advances R during end-of-pass refinement. This is a 1-minute repeated-file soak, not live-source evidence; live ingest and 5/10/30-minute soaks remain open.
  - **Progress:** URL analysis uses one shared audio/video demux after one metadata inspection; the API accepts HTTP(S)/RTSP(S), redacts credentials/query tokens, and exposes `DELETE /v1/streams/{id}`. RTSP defaults to `drop_oldest` and rejects `block`. The HTTP A/V smoke processed 1,139 packets through one decoder session; the fake-runner lifecycle smoke is in `benchmarks/reports/api_live_url_lifecycle_smoke.json`. A local MediaMTX+FFmpeg RTSP smoke is recorded below. Stalled-read cancellation is now measured on loopback RTSP; physical-camera behavior and sustained live priority remain open; API reconnect is covered below; shared admission across bounded lanes is documented in `benchmarks/reports/shared_load_priority_scheduler.md`.
- **Depends:** F4.03, F1.03.
- **Проверка:** `benchmarks/reports/replay_ingest_smoke.json`, `benchmarks/reports/analyzer_av_ring_smoke.jsonl`, `benchmarks/reports/analyzer_scheduler_smoke.jsonl` и `benchmarks/reports/analyzer_pressure_smoke.jsonl` фиксируют replay ring, параллельный A/V capture producer с packet→ring→decode, L2 scheduler и critical pressure. A/V CPU smoke занял 13.21 с; 50 ms process-tree sampler измерил 2.43 GB peak RSS на одном процессе. C/E=20 000 мс, 0 drops, video queue stall 342 ms, L1 дошёл до конца, а 14 L2 задач были отклонены с backpressure. Video-only normal path завершил L2; при memory limit 1 byte отклонены 9 L2 задач, L1 сохранён. Finite-file прогоны не измеряют sustained RAM при 2×/5× и не закрывают DoD. Additional smoke outputs: `benchmarks/reports/analyzer_shared_interleave_smoke.jsonl`, `benchmarks/reports/audio_only_shared_interleave_smoke.jsonl`, `benchmarks/reports/video_only_shared_interleave_smoke.jsonl`, summarized in `benchmarks/reports/analyzer_shared_interleave_smoke.md`.
- **DoD:** на 2× и 5× искусственной нагрузки full-stack система ограничивает RAM и своевременно сигнализирует degradation.

- **2026-10-26 progress:** `PrefetchTelemetry.current_depth` now reports live queue occupancy; end-of-media admission uses it rather than stale peak depth. The 2x/5x pressure recheck had zero scheduler rejects, prefetch drops, or coverage misses. Loopback RTSP is covered; physical-camera behavior and sustained real-time throughput remain open.
- **2026-10-26 live loopback 2x/5x:** `benchmarks/reports/live_rtsp_priority_terminal_20261026.md` summarizes the repeatable MediaMTX + FFmpeg API run and links its raw `report.json`. Both scales reached capture-ready and all sessions reached terminal `stopped`. This run set `SHSD_MEMORY_LIMIT_BYTES=1` to force the critical-admission path; it is a synthetic pressure signal, while process-tree RSS was measured separately at 2.29 GiB (2x) and 2.33 GiB (5x). At 2x, queues reported 655 dropped prefetch items and 33 scheduler rejects; at 5x, 5,204 drops and 76 rejects. The 5x API latency p95/max was 726/3,658 ms, and completed L1/L2 coverage ended at 15.9–25.2 s while capture cursors reached 38.3–50.8 s. This proves bounded memory and visible overload behavior on loopback RTSP, not sustained realtime processing.
- **2026-10-26 60-second live loopback soak:** `benchmarks/reports/live_rtsp_priority_60s_20261026.md` and raw `report.json` extend the 2x/5x pressure check to 60 seconds. All seven streams reached terminal `stopped`; peak process-tree RSS was 2.32 GiB at 2x and 2.34 GiB at 5x. The 5x scenario reported 8,430 shared-prefetch drops and 112 scheduler rejects; API polling latency p95/max was 10.87/11.30 seconds and graceful stop took 66.46 seconds. This supports bounded memory and explicit overload reporting, while showing that 5x responsiveness is not timely and real-time throughput is not established.
- **2026-10-26 progressive-watermark 60-second loopback:** `benchmarks/reports/live_rtsp_priority_progressive_commit_60s_20261026.md` and its raw JSON verify pre-stop R[L1] after fixing leading PTS gaps and separating capture horizon updates from semantic completions. All 2x/5x streams stopped cleanly; 2x pre-stop R[L1] reached 60.7–64.1 s with 0.60 s stop wait, while 5x reached 31.1–41.1 s with 27.63 s stop wait and 2,449 prefetch drops. Peak RSS was 2.33/2.35 GiB; no L1 failures or scheduler rejects. 5x continuous real-time processing is not established.
- **F6.01 still open:** two-minute loopback acceptance bounds peak process-tree RSS at 2.32 GiB for 2x and 2.35 GiB for 5x and records pressure degradation. At 5x the default profile's median L1 lag rises from 6.1 to 55.1 s over the soak, with 81.7% final R/L1 issue spans, so sustained real-time processing is not established. Twelve threads reduce lag but raise final R/L1 issue spans to 89.6%. Physical-camera behavior remains unverified: FFmpeg enumerated Meta Quest and OBS video devices earlier, but no camera frames were captured; current Windows Camera enumeration is empty. Keep the parent unchecked until physical-camera capture is recorded. See `benchmarks/reports/live_rtsp_soak_2m_20261026.md`.
- **2026-10-26 live Qwen 60-second CPU recheck:** `benchmarks/reports/live_qwen_online_60s_20261026.md` compares cold/warm four-thread Qwen, warm twelve-thread Qwen, and a warm twelve-thread no-L3 control. Without L3, pre-stop C/E/R1/R2 was 42.0/40.0/42.0/35.1 s and post-stop wait 1.2 s; with Qwen L3, C/R2 was 43.0/35.6 s and wait 16.0 s. Capture is similar, so Qwen is not established as the capture-throughput bottleneck. The no-L3 run used 2.333 GiB peak RSS versus 3.263 GiB with Qwen and both runs had zero decoder-ingest drops. L1/L2 lag p50 was 18.0/17.6 s without L3 and 18.8/16.8 s with 12-thread Qwen. The result narrows the throughput investigation to the path before narration; F6.01 remains open for 2x/5x and physical-camera acceptance.
- **2026-10-26 graceful-stop recheck:** `benchmarks/reports/live_rtsp_priority_graceful_stop_final_20261026.md` records a cold-cache 25 s 2x/5x loopback run (4 threads, 4 GiB pressure threshold). All seven streams reached terminal stop with metrics, no L1 worker errors or pending final coverage, and final C/E/R[L1] aligned. Peak RSS was 2.37 GiB; 5x pre-stop R[L1] ranged from 53 ms to 10.1 s and end-to-end elapsed/final-media ratio was 1.18–1.28, so realtime throughput is still not established. The run also fixes an atomic watermark revision race and graceful decoder shutdown after DELETE. Physical-camera and sustained-throughput acceptance remain open.
- **2026-10-26 60-second live soak:** `benchmarks/reports/live_rtsp_priority_graceful_stop_60s_20261026.md` records 2x/5x loopback with four CPU threads and 4 GiB threshold. All seven jobs stopped without errors; final C/E/R[L1] aligned with zero pending coverage. Peak RSS was 2.42/2.36 GiB; 5x had 5,255 prefetch drops and pre-stop R[L1] from 84 ms to 10.2 s. End-to-end elapsed/final-media ratio was 1.09?1.15, so sustained realtime remains unproven. The report identifies shared embedding admission/fairness profiling as the next throughput path; physical camera validation remains open.
- **2026-10-26 local RTSP smoke:** MediaMTX + FFmpeg looped `av_sync_20s.mp4` at realtime into the API. The real RTSP job used `drop_oldest`, prefetch capacity 8, and `sampling_profile=adaptive`; one decoder demux handled 1,822 packets (1,506 audio, 316 video), final C/E/R reached 34,156 ms, and API stop completed in 722 ms. Prefetch recorded 77 dropped queue items with zero ingest drops. The temporary server and publisher were stopped after the smoke. This verifies local RTSP ingest and cooperative stop during active delivery; physical-camera behavior remains open; API RTSP reconnect is covered by the later smoke. Stalled-read cancellation was measured in the later report below.
- **2026-10-26 stalled-read and watermark smoke:** `benchmarks/reports/rtsp_stalled_read_stop_smoke.md` records a loopback read-gap stop: the video cursor held at 19,067 ms while the stream remained running, DELETE returned in 9 ms, and `stream.stopped` followed 418.9 ms later without an error. A post-change video-only RTSP WebSocket replay advanced overall C with live progress (1,051, 2,051, and 3,051 ms), matching the video cursor while the missing audio track was marked unavailable. Physical-camera behavior remains open; publisher restart is covered in the later report.
- **2026-10-26 runtime load sampling:** `analyze_media()` now feeds nonblocking queue, C−E lag, host CPU, and process-tree RSS samples to the shared `RuntimeLoadController` during interleave; sampling is capped at 250 ms and includes a drained-queue observation before post-pass L2 admission. `benchmarks/reports/runtime_load_sampling_smoke.md`: 20 s A/V run reached C/E/R(L1)/R(L2)=20,000 ms, committed 14 L2 events, recorded five runtime observations, and had zero scheduler rejects; peak process-tree RSS was 2.43 GB. This is a finite-file admission smoke, not live-priority or sustained-latency evidence.
- **2026-10-26 embedding worker smoke:** `analyze_media()` now submits audio and frame encoding to one bounded serial worker, then applies results in submission order on the consumer thread so `TemporalEventReducer` and `EventStore` remain single-threaded. A scene-cut barrier drains older embeddings before updating the reducer. `benchmarks/reports/analyzer_embedding_worker_smoke.md` and `.jsonl`: 20 s A/V fixture, 9/9 jobs completed, max outstanding 2/2, 36 matches, 34 event revisions, C/E/D/R=20,000 ms, 0 worker errors. This verifies boundedness and coverage, not a speedup versus synchronous inference; load-aware L1 scheduling, priorities, and live soak remain open.
- **2026-10-26 scale checks:** `fullstack_embedding_worker_1m.md` is a warm-cache 1-minute 2x/5x run: aggregate RTF 0.401/0.184, mean CPU 1.95/4.80 cores, peak RSS 4,676/11,695 MiB, and zero drops/coverage misses/L2 rejects. Fixture embeddings were cache hits, so this does not measure cold inference. `fullstack_embedding_worker_cold_cache.md` isolates cache per stream for one cycle: per-stream RTF 1.76–1.77 at 2x and 2.01–2.03 at 5x; 5x rejected 14 L2 jobs per stream under load, while all L1/L2 watermarks reached 20,000 ms and no media coverage was missed. Cold single-cycle results identify profile initialization and uncached embeddings as the real-time bottleneck; they are concurrency smokes, not endurance soaks.

- 2026-10-26 vision throughput experiment: added opt-in `standard` (280 tokens) / `compact` (140 tokens) profiles through CLI and API; isolated-cache A/B reduced visual inference from 4.31 s to 1.39 s on one selected frame while one uncertain top label changed. Synthetic-only evidence; keep standard as default. Report: `benchmarks/reports/vision_profile_ab_20261026.md`. A video-only overlapping-window stale-revision failure was also fixed; sustained 2x/5x and natural-media quality remain open.

- 2026-10-26 compact live soak: the 60 s 2x loopback run had 503 shared-prefetch drops / 0 scheduler rejects (standard comparison: 1,618 / 35); at 5x it still had 5,918 drops / 28 rejects and up to 40.1 s observed L1 lag. Final watermarks aligned only after drain. Sustained 5x and physical-camera acceptance remain open; see `benchmarks/reports/live_rtsp_vision_compact_60s_20261026.md`.
- **2026-10-26 shared embedding dispatch:** API streams using one pooled provider now share a bounded round-robin inference queue (64 pending jobs, 256 retained source summaries), and API shutdown drains analysis/refine work and metadata before closing it. Worker fairness/bounds, source-stat eviction, and API shutdown have unit coverage. In the 25 s compact RTSP check, 5x capture became ready in 12.84 s and all five sources stopped; the previous worker trace did not reach capture-ready within 127.21 s. Long provider-lock worker time fell from 623.1 s over 14 jobs to 36.4 s over 9 jobs, with 36.2 s measured model inference in the new run. The new per-stream elapsed/media ratio was still 1.17–1.34, and the short cold-cache 2x ratio was 1.63–1.65. Since the previous run continued until its capture timeout, aggregate drops and wall time are not a direct A/B. Keep F6.01 open; see `benchmarks/reports/live_rtsp_shared_dispatch_25s_20261026.md` and its raw `report.json`.
- **2026-10-26 60-second dispatcher soak:** all 2x/5x loopback streams stopped; peak process-tree RSS was 2.31/2.33 GiB. At 5x, pre-stop L1 lag was 40–41 s and per-stream RTF remained 1.14–1.23. The new run removed nearly all provider-lock wait (77.1 s worker time for 76.5 s inference), but drops/rejects and end-to-end lag did not improve versus the earlier compact soak. Fair dispatch addresses starvation; model throughput remains limiting. See `benchmarks/reports/live_rtsp_shared_dispatch_60s_20261026.md` and its raw `report.json`.
- **2026-10-26 CPU thread A/B:** the isolated model test favored 8 threads for audio and 12 for video. In the 60 s live 5x comparison, 12 threads improved RTF to 1.08–1.16 versus 1.14–1.23 at four threads, but peak L1 lag rose from 41.3 to 48.6 s, prefetch drops from 6,074 to 6,864, and scheduler rejects from 37 to 47. Keep four as default until a balanced profile is demonstrated; full measurements: `benchmarks/reports/embedding_thread_scale_live_20261026.md`.

### F6.02 — Adaptive sampling [P1]
- [x] Опциональный `standard/adaptive` profile управляет audio embeddings по межоконным изменениям loudness, VAD fraction, spectral centroid и onset count; video embeddings — по low-resolution frame difference.
- [x] Heartbeat ограничивает тихий/статичный интервал 15 секундами; пропуски помечаются `adaptive_sampling` в E watermark. CLI и API сохраняют выбранный profile.
- [x] L1 `window_match` rows record the combined sampling novelty, signal delta, compatible embedding cosine/novelty, reference window, and method version. Similarity is not a probability; only accepted L1 claims advance the bounded novelty baseline.
- [x] Adaptive video selection now reuses its 160×90 RGB sample for the corresponding L0 frame-difference pass, avoiding a duplicate PyAV frame conversion; unit coverage verifies one conversion per sampled frame in this path (`tests/unit/test_analyze.py::test_adaptive_video_reuses_the_low_resolution_frame_for_l0`).
- [x] Проведён exploratory A/B на 40 natural windows с provisional source-description labels и repeated CPU A/B на 180 s synthetic quiet-dither control; см. `benchmarks/reports/adaptive_sampling_natural_delta.md` и `benchmarks/reports/adaptive_sampling_delta_quiet_paired_180s_20261026/sampling_profiles_ab.md`.
- **A/B findings:** Межоконный delta sampler выбрал 39/40 natural windows (19/20 source-labeled speech positives and 20/20 negatives); это 2.5% меньше embeddings, но provisional speech admission recall — 95%, без пропуска negative windows. Метки выведены из описаний источников и ещё не подтверждены прослушкой. На 180 s one-LSB synthetic quiet-dither control с уникальными окнами и изолированным per-run cache выбраны 12/36 embeddings; медианы трёх чередуемых пар показали 51.3% меньше model inference, 65.9% меньше audio-consumer work, 41.2% меньше process-tree CPU и 28.2% меньше wall time. В отдельном 600 s pure-digital-silence запуске выбраны 40/120 embeddings и audio-consumer stage снизился на 11.7%, но CPU вырос на 1.0%; все embedding-вызовы попали в cache, поэтому inference не измерялся. Естественная экономия без потери recall не подтверждена; профиль остаётся opt-in.
- **Depends:** F2.01, F6.01.
- **DoD:** частичный результат; delta-based admission, heartbeat, coverage, and exploratory A/B are recorded. Natural labels need independent listening review, and representative media savings/recall remains unverified. Do not make adaptive sampling the default.

### F6.03 - Full-stack CPU benchmark [P0]
- [x] Run repeated replay at 1, 5, 10, and 30 minutes for 2x/5x stream scale.
- [x] Complete the 30-minute 2x/5x A/V baseline soak and review RTF, lag, RAM, CPU, disk queue depth, and missed events.
- [x] Compare GigaAM ASR on/off, L3 template/Qwen, and dynamic text-hypothesis profiles; record quality and runtime limits.
- **Progress:** The 1-, 5-, and 10-minute A/V soaks are in `benchmarks/reports/fullstack_av_1m_soak.md`, `fullstack_av_5m_soak_retry.md`, and `fullstack_av_10m_soak.md`. The 10-minute L0/L1/L2 run processed 1,400 media-seconds at 2x and 3,100 at 5x with zero coverage misses and zero ingest/prefetch drops. Its scheduler rejects (154 at 2x, 1,498 at 5x) were traced to stale peak prefetch depth at end of finite-file analysis; admission now uses current depth. `fullstack_pressure_recheck.md` verifies zero rejects and zero coverage misses at both scales after the fix. The old 10-minute report's rejects are retained as historical evidence and are not the baseline for the corrected analyzer.
- **Feature A/B:** `benchmarks/reports/fullstack_feature_ab.md` compares L3 template/Qwen, GigaAM ASR off/on, and dynamic `music_presence` hypotheses. Qwen measured 30.9 tokens/s at 2x and 12.3 at 5x, but per-stream RTF was 1.288/1.299 and 1.704/1.708 (p50/p95), respectively. Template mode stayed below RTF 1 and built source-only fallbacks in under 0.05 ms p95. ASR increased peak process-tree RSS to 7,946 MiB at 2x and 19,834 MiB at 5x on a 5.016-second fixture. Dynamic proposals selected zero candidates; at 5x, all five Qwen proposals timed out at 10 seconds. The 28-window natural speech-presence evaluation had the same ranked accuracy (17/28) and zero accepted coverage in both modes.
- **Warm-cache 30-minute repeated-file baseline:** `benchmarks/reports/fullstack_av_30m_soak.json` and `.md` (2x then 5x, L0/L1/L2). The 2x scenario completed 105 cycles / 4,200 media-seconds in 1,811.5 s: per-stream RTF p50/p95/max 0.859/0.873/0.885, mean 1.91 CPU cores, peak process-tree RSS 4,694 MiB, disk queue p95/max 0/5, and zero coverage misses, ingest drops, prefetch drops, or scheduler rejects. The 5x scenario completed 92 cycles / 9,200 media-seconds in 1,817.6 s: per-stream RTF 0.981/0.991/1.002, mean 4.75 CPU cores, peak RSS 11,712 MiB, disk queue p95/max 0/6, and zero coverage misses, ingest drops, prefetch drops, or scheduler rejects. The finite-file lag p95 reached 20 s at both scales and returned to zero at final watermarks; interpret it as within-pass progress backlog, not a live-camera latency measurement. The model/profile initialization stage took 16,223 ms in a representative cold CLI cycle; per-pass audio and video consumer work was about 202 ms each and L2 state refinement 112 ms. A sampled first-cycle timeline had nine embedding records and all nine were cache hits, so these 30-minute RTF values measure repeat-file warm-cache behavior, not unique-media throughput. See the isolated-cache comparison below before making realtime claims.
- **Post-worker cold-cache check:** `benchmarks/reports/fullstack_embedding_worker_cold_cache.md` separately measures one 20 s cycle per stream with unique embedding caches. With 4 threads per process, per-stream RTF was 1.76–1.77 at 2x and 2.01–2.03 at 5x; each process spent 13.6–15.8 s on profile initialization and about 19.3–22.0 s on media embeddings. At 5x the load controller rejected 14 lower-priority L2 jobs per stream while L1/L2 terminal watermarks still completed with zero dropped/failed media coverage. A 5x follow-up at 2 threads took 55.6 s (RTF 2.76–2.78 per stream), slower than 4 threads; see `fullstack_embedding_worker_cold_cache_t2.md`. The 30-minute baseline reused warm cache across processes and is not a cold-inference claim.
- **Decision:** `docs/adr/ADR-001-next-version-performance.md` retains EmbeddingGemma2 and CPU inference, declines projector training and NCM changes, and recommends reducing repeated process/model startup and completing the shared L1 scheduler before considering another encoder. The near-1.0 5x p95 leaves limited headroom; the measured degraded profile keeps ASR, Qwen L3, and iterative proposals opt-in.
- **Depends:** F4.05, F6.01.
- **DoD:** Reproducible JSON and Markdown with CPU, RTF, lag, RAM, disk queue, and coverage evidence. Any RTF above 1 must include the measured bottleneck and a degraded-profile decision.

### F6.04 — Принять решение о следующей версии [P1]
- [x] Сопоставлены качество и скорость; warm-cache replay and cold unique-media results are separated. The isolated-cache smoke measured RTF above 1 at both 2x and 5x, so realtime unique-media processing is not established; no encoder replacement is accepted without a controlled quality comparison.
- [x] Encoder replacement отклонён: текущие данные не показывают quality gap, который оправдал бы замену; сначала нужны persistent model process и общий L1 scheduler.
- [x] Projector training отклонён по умолчанию: нет представительной evidence of embedding information loss.
- [x] NCM не пересматривается без отдельного comparative benchmark и ADR.
- **Depends:** F6.03.
- **DoD:** принятые и отвергнутые подходы записаны в `docs/adr/`.

---

## 2. Минимальная последовательность задач для coding-агентов

```text
F0.01 → F0.02 → F0.03
   ↓          ↓
F0.04 → F1.01 → F1.02 → F1.03
                 ↓
             F2.02 → F2.03 → F2.04 → F2.05 → F2.06
                 ↓                        ↓
             F2.01 ───────────────────→ F3.01
                                          ↓
                              F4.01 → F4.02 → F4.03 → F4.04 → F4.05
                                                          ↓
                                                     F5.01 → F5.02
                                                          ↓
                                                     F6.01 → F6.03
```

Параллельно по готовности зависимости: F3.02/03/04/05, F5.03, F6.02.

### Первый вертикальный срез (не откладывать)

- [x] Один реальный MP4, несколько audio embeddings и ключевых кадров.
- [x] Список кандидатов на музыку/действия и cosine score + margin.
- [x] L1 event JSON с доказательством и `unknown` при неоднозначности.
- [x] Qwen русское L3 по этим событиям без добавления фактов.
- [x] CLI печатает C/E/R и measured latency.

**Проверка вертикального среза, 2026-10-26:** `benchmarks/reports/poc_real_mp4_20261026.md` использует лицензированный 20-секундный MP4 *Tears of Steel*, 9 эмбеддингов, 36 L1 matches с cosine/margin, 6 Qwen captions и финальные C/E/D/R=20 000 мс. Все caption schema checks и ссылки на event revisions прошли; неподдержанных утверждений не опубликовано. Полный JSONL и event store находятся в `benchmarks/reports/poc_real_clip_20261026/`.

Без этого прототипа **не** начинать большой UI, интерактивный поиск по десятиминутной истории, NCM-интеграцию или обучение.

---

## 3. Минимальная тестовая матрица

| Тест | Содержание | Должно произойти |
|---|---|---|
| T01 | Тишина и неподвижный кадр | Нет выдуманной музыки и действий |
| T02 | Музыка без речи | Music events; ASR off не влияет |
| T03 | Речь поверх музыки | Возможны music и speech события одновременно |
| T04 | Музыкальная смена на 7-й секунде | Новое событие около границы; правильный порядок |
| T05 | Montage cut без звукового изменения | Только visual change, нет ложного sync |
| T06 | Звуковой удар при cut | AV relation только при независимых evidences |
| T07 | Audio отсутствует | `unavailable`, не «тишина» |
| T08 | Seek назад | Новый epoch; нет stale overlay |
| T09 | L3 задержан на 60 сек | C и L1 продолжают; R[L3] отстаёт |
| T10 | Late worker ответ старой revision | Не перезаписывает новую |
| T11 | Ring переполнен удержанными task chunks | Spill или explicit dropped; без роста RAM |
| T12 | Невозможно различить инструменты | `unknown/uncertain`, не выдуманный точный инструмент |
| T13 | Повторяемая сцена 2 минуты | Не создаются десятки одинаковых captions |
| T14 | Подмена аудио у видео | Аудиопризнаки меняются; визуальные остаются |
| T15 | Offline mode без сети | Нет внешних запросов и скрытых скачиваний |

---

## 4. Definition of PoC success

### Минимальный успех

- [x] На **реальном CPU**, без training, cloud и GPU можно запустить входное видео.
- [x] Структурные L1/L2 события основаны на настоящих embeddings, детекторах и optionally ASR.
- [x] L3 описывает на русском и с таймкодами, только из подтверждённых событий.
- [x] Результаты публикуются не блокируя дальнейший захват.
- [x] Воспроизводимые JSON события, уровни, ревизии, evidence.
- [x] Есть профилированный lag и latency; если realtime не достигнут — это явно указано.

**Проверка минимального успеха:** локальный offline CPU MP4 run и 60-секундный synthetic RTSP API run зафиксированы в `benchmarks/reports/poc_real_mp4_20261026.md` и `benchmarks/reports/live_rtsp_priority_progressive_commit_60s_20261026.md`. Условия подтверждены в измеренном окружении; устойчивый live throughput на 5x и реальная камера остаются отдельными открытыми вопросами ниже.

### Расширенный успех

- [x] 600-second rolling window with bounded memory and explicit gaps. Evidence: `tests/unit/test_ring.py::test_ring_bounds_memory_over_thirty_minutes_of_media_time` runs 1,800 seconds of source time with a 600-second window and 1 MB ring cap; `tracemalloc` peak stays below 8 MiB. `test_ring_emits_dropped_when_memory_and_spill_limits_are_full` verifies an explicit `dropped` result.
- [x] UI c C/R и дорожками по модальностям и уровням.
- [x] Adaptive sampling reduces measured cost on a controlled 180 s synthetic near-silence A/B: 24/36 audio embeddings skipped; across three paired runs, model inference fell 51.3%, audio-consumer work 65.9%, process-tree CPU 41.2%, and wall time 28.2%. The 40-window source-described natural set admitted 39/40 windows at provisional 95% speech admission recall; labels remain unreviewed, so representative natural-media savings and recall are unestablished. Pure digital silence with identical windows lowered audio-consumer work by 11.7% but raised CPU by 1.0% over one 600 s run; cached outputs meant it did not measure model inference. See `benchmarks/reports/adaptive_sampling_delta_quiet_paired_180s_20261026/sampling_profiles_ab.md`, `benchmarks/reports/adaptive_sampling_delta_silence_ab_600s_20261026/sampling_profiles_ab.md`, and `benchmarks/reports/adaptive_sampling_natural_delta.md`.
- [x] Документированы наблюдаемые precision/unknown rates музыкальных и визуальных claims на synthetic fixtures.
  - **Progress:** The eight synthetic PoC timelines show music-presence 0/10 accepted (10/10 uncertain), all visual-semantic axes 0/36 accepted (36/36 uncertain), and undefined precision because neither domain has accepted positive predictions. No false accepted music/visual claims were observed against fixture labels; this is not natural-media accuracy. Natural-media precision, recall, and calibration remain unmeasured. See `benchmarks/reports/poc_manual_review.md`.
- [x] 60-second live soak documents both the throughput deficit and the concrete engineering path for the tested CPU configuration; see `benchmarks/reports/live_rtsp_priority_graceful_stop_60s_20261026.md`. The run does not claim realtime acceptance.

## 5. Запреты на scope creep

**Не добавлять в Todo.md текущего PoC:** training Projector, LoRA, synthetic training dataset, adapter embedding→Qwen, direct NCM weights integration, персональную диаризацию, распознавание музыкального произведения, точную harmonic transcription, обязательные облачные сервисы, «реалтайм гарантирован на любом CPU».

Такие изменения требуют отдельной ADR, новых критериев и явного решения владельца проекта.

- **2026-10-26 prefetch stride retry:** A selected video frame discarded by bounded prefetch releases the selector stride; adaptive sampling also rolls back its last selected timestamp, and the dropped frame remains explicit in E coverage. Regression tests verify retry behavior. The 60 s 2x/5x follow-up stopped all seven streams without errors and aligned final C/E/R[L1]; it recorded 21 selected video embedding opportunities at 5x, with pre-stop R[L1] from 0.35 to 15.33 s and end-to-end ratios above 1. Sustained real-time and physical-camera validation remain open. See `benchmarks/reports/live_rtsp_priority_prefetch_retry_60s_20261026.md`.

## Current user-directed quality work (2026-10-26)

1. **Real 90-second music/video pass:** `benchmarks/reports/real_video_quality_asr_recheck_20261026/report_real_video_quality.md` contains every latest L1/L2 claim, all 17 L3 captions, five final ASR windows, and links to the exported CSVs plus UTF-8 timeline. The CPU run completed in 87.626 s and reached final C/E/R=90,000 ms. It fixes an offline ASR self-gating failure: local-file speech windows are held in a bounded buffer (up to 32 windows, sized to known duration) and transcribed after the main media pass; URL/live ASR retains shared backpressure. All five windows now return text with zero drops, but the raw transcript is poor and unreviewed. Quality is still not acceptable: Qwen repeated a generic scene-change caption eight times, nine fallbacks repeat source-only scene claims, 108 matches were skipped, and L2 coverage shows runtime backpressure. Diagnosis and baseline/fix comparison: `benchmarks/reports/offline_asr_backpressure_fix_20261026.md`.
2. **Semantic Matcher diagnosis:** `benchmarks/reports/music_prompt_probe_20261026.md` compares four exact music prompt pairs over 18 real windows. Baseline positive/negative cosine means were 0.732380/0.732023, mean absolute margin 0.009526 against the 0.05 policy, and 0/18 windows were accepted. The full real-video rerun shows all 18 ambient-sound and impact-sound windows uncertain; speech has 1/18 accepted; music has 0/18 accepted; all six sampled visual windows remain uncertain on person, setting, scene style, and screen text. For top-gap axes, 17/18 speech and all 18 ambient, impact, music, person, setting, screen-text rows fall below the 0.05 margin; for scene-style, 4/6 scores fall below 0.60 similarity and all 6 fall below its 0.05 distance-above-threshold margin. One alternate music prompt pair accepted a music-absent decision; this is not correctness evidence. Production prompts and thresholds remain unchanged pending independent labels. Exact per-axis thresholds, margin basis, candidate scores, and Russian hypotheses are in `semantic_match_scores.csv`.
3. **Music development:** `benchmarks/reports/music_dynamics_probe_20261026.md` scores vocals, percussion, bass, energy, tempo, and instrument-family candidates separately on the same windows. The production music gate blocks detail output because music_presence is uncertain in 18/18 windows. Candidate ranking changes and acoustic energy/spectrum measurements are diagnostic only; instrument and rhythm transitions have not been validated.
4. **Live CPU with Qwen:** URL/live mode commits stable L1 events into separate bounded online L2 and Qwen L3 workers, with coverage barriers and CAS revisions. The 60-second RTSP comparison in `benchmarks/reports/live_qwen_online_60s_20261026.md` includes a warm 12-thread no-L3 control: pre-stop C/E/R1/R2=42.0/40.0/42.0/35.1 s, 20 live L2 revisions, and 1.2 s post-stop wait; the paired Qwen run reached C/R2=43.0/35.6 s, emitted 15 live L2 revisions and 7 captions, and waited 16.0 s after stop. Similar capture progress means Qwen is not established as the capture bottleneck, although it adds about 0.93 GiB peak RSS. The older 35-second run in `benchmarks/reports/live_qwen_online_smoke_20261026.md` emitted 3 L2 events and 2 captions; the first caption arrived at 25.877 s. These runs prove online execution, not sustained realtime. F6.01 remains open for 2x/5x and physical-camera acceptance.

The independent 40-clip listening labels remain pending. The user confirmed they will send the CSV; current source-derived labels do not close F3.03.


**2026-10-26 Qwen v2 real-source rerun:** `benchmarks/reports/qwen_l3_dedup_20261026/report.md` now exports every latest L1/L2 claim with its Russian description and all 18 L3 output/dedup rows for the 90-second Tears of Steel excerpt. Qwen emitted two generated captions, 16 adjacent duplicate requests were coalesced, with zero fallback and zero unsupported claims. The text remains generic and does not describe music structure or dialogue. Music remains uncertain in 18/18 windows; neighbor recheck confirmed 0/62, abstained 10, and skipped 52. The report includes the candidate score/margin distribution, the music-development probe, and raw CSV/JSONL artifacts. This reduces duplicate generation and fallback output, but it does not make descriptions more specific or close live acceptance.

**2026-10-26 Qwen v2 live follow-up:** `benchmarks/reports/live_qwen_v2_60s_20261026/report.md` measures the updated narrator on a 60-second, 1x loopback RTSP publication. The caption appeared before stop (lag 20.839 s), but C reached 41.828 s, R[L1]/R[L2]/R[L3] reached 35.120/25.120/29.745 s, and live lag p50 was 22.270 s for L1 and 17.733 s for L2. Qwen generated one generic caption; shared prefetch dropped 503 frames/jobs. Terminal drain was 3.254 s; media-ingest packet drops were zero. This remains below realtime and does not close F6.01. The measured run had no embedding-cache hits; do not attribute its changes solely to narrator deduplication.
