# Todo.md — SHSD: активный backlog качества и realtime

> **Версия 0.2 · 26.10.2026.** Все новые задачи ниже **открыты** до предъявления воспроизводимых доказательств. Прежний F0–F6 чеклист (исторически 157/159) [архивирован без изменений](docs/archive/2026-10-26-pre-multimodal-review/Todo.md). Эта цифра не измеряет готовность продукта.
>
> Цель: [Workspace.md](Workspace.md); правила агента: [Agents.md](Agents.md); протокол: [docs/experiments/av-bridge-evaluation-protocol.md](docs/experiments/av-bridge-evaluation-protocol.md).

## Обязательные правила

- **P0** — достоверность, traceability, оценка качества и live-блокеры; **P1** — детализация; **P2** — исследование альтернатив.
- CPU-only/offline production; EmbeddingGemma 2 + Qwen3-0.6B сохраняются. **Не обучать** модели, projector или LoRA, не собирать training corpus без отдельного одобренного ADR.
- Малый набор независимых **оценочных** ручных меток обязателен; он не является обучением. Cosine не вероятность; accepted-by-policy не human-verified.
- Не закрывать checkbox без ссылки на тест/сырые JSON/benchmark, git SHA, версий моделей, конфигурации, точных команд и негативных примеров. `not run` писать явно.
- Отчёты класть в `benchmarks/reports/`; при изменении схем — документировать совместимость, миграцию и regression tests.

## F7 — Достоверность музыки и смысловой traceability

### F7.01 — Разделить music_possible и music_confirmed [P0]
- [ ] Проверить `src/shsd/semantic/temporal.py::_music_scene_supports_details`, `analyze.py` и текущие hypothesis configs. Зафиксировать случаи, где `conversation_dominant` accepted, но music alternative с cosine≥0.60 открывает публикацию музыкальных деталей.
- [ ] Сохранить возможность **внутреннего** coarse-to-fine поиска при `music_possible`, но **не публиковать** детали без отдельно подтверждённой музыкальной предпосылки и собственного evidence по оси.
- [ ] Учесть реальное наложение речи и фоновой музыки: conversation-dominant не означает music-absent; разрешать подтверждённые music+speech детали при независимом evidence.
- [ ] Явно сохранять premise state и provenance в claim/event, без разрушения L1/L2 revisions и старого JSONL.
- [ ] Тесты: conversation-only hard negative; music-only; music+speech; uncertain music; conflicting top/runner-up; 01:10–01:25 из `Tears of Steel`.
- **DoD:** ни одна опубликованная music detail не опирается **только** на runner-up music candidate; все accepted details имеют независимый premise/evidence; нет необоснованного запрета реального overlap; регрессии проходят.
- **Depends:** baseline `20acb747`.

### F7.02 — Исправить L2→L3 claim accounting и фактическое покрытие [P0]
- [ ] Проверить `src/shsd/captions/narrator.py`: `used_claim_ids=tuple(sorted(request.source_ids))` для generated/fallback сейчас **не показывает**, какие claims реально выражены.
- [ ] Развести `input_claim_ids`, `expressed_claim_ids`, `omitted_claim_ids` и неопределённое соответствие; ввести проверяемую политику semantic claim coverage, без автоматического присвоения всех входных IDs.
- [ ] Для важных accepted L2 деталей настроить приоритет/группировку narration, чтобы Qwen мог выразить их естественно по-русски; осознанные пропуски при лимите токенов фиксировать, не маскировать.
- [ ] Отдельно проверять unsupported factual additions (не только ключевые слова) и корректность fallback; поддержать ASR/visual claims и source-only mode.
- [ ] Регрессия: `percussion_present` в 01:10–01:25, который Qwen в текущем отчёте не произнёс; negative test, где Qwen говорит только про разговор, не должен помечать percussion `expressed`.
- **DoD:** выходная схема и UI/API/JSONL согласованы; omission измерим; generated caption не получает ложные used IDs; добавлены unit/integration tests на partial coverage, paraphrase, unsupported claims и fallback.
- **Depends:** F7.01 для publishable claims.

### F7.03 — Независимые ручные метки и слепая оценка [P0]
- [ ] Подготовить **10–20** независимых размеченных интервалов разных аудио/видео, включая 75–85 с `Tears of Steel`, music+speech, speech-only, ambience, music-only, transitions, визуальные действия. Это **оценка**, не training.
- [ ] Зафиксировать схему: intervals, scene class/overlap, percussion/bass/vocals/instrument families, onset/offset/energy changes, visual entities/actions, unknown, evidence, annotator, rights/source.
- [ ] Проверить разметку **до** просмотра предсказаний или пометить non-blind; сохранить разногласия, source-separated splits, hard negatives и audio/video swaps.
- [ ] Написать eval runner: precision/recall/F1, accepted coverage/abstain, false-premise/false-detail rates, semantic transition accuracy, L2→L3 expressed/omitted, unsupported claims; raw per-interval errors.
- **DoD:** schema + label provenance + воспроизводимый eval report; если исходных файлов/разметки нет — `blocked`, не заменять ручные метки score-based псевдоразметкой.
- **Depends:** можно начать параллельно F7.01/02.

### F7.04 — Повторить контролируемый 90-секундный A/B [P0]
- [ ] Одинаковые источник, ревизии моделей, thresholds, CPU threads, audio windows; сравнить `20acb747` с F7.01+02 по независимым меткам.
- [ ] Отчёт отдельно: 4/18 scene accepted (все conversation), 1 L2 percussion, 0 accepted semantic transitions, 3 L3 — **baseline**, а не accuracy target.
- [ ] Сохранить source intervals, L1/L2 decisions, evidence, Qwen text, `input/expressed/omitted`, fallback и latency; отметить label-free показатели.
- **DoD:** машинно-читаемый diff и Markdown с точными false positives/omissions, без пороговой подгонки по test.
- **Depends:** F7.01–03.

## F8 — Динамика и сюжет

### F8.01 — Семантические музыкальные переходы [P1]
- [ ] Проверять на соседних окнах появление/исчезновение/смену музыкального слоя; сохранять temporal support и стабильный ID слоя, отличать acoustic novelty от semantic transition.
- [ ] Раздельные оси: percussion, bass, vocals, timbre, instrument family, energy, tempo feel; никаких выводов о точном BPM/инструменте без подтверждения.
- [ ] Добавить тесты с известным onset/offset и negative windows (речь, шум, монтаж), измерить precision/recall на размеченных примерах.
- **DoD:** подтверждённые переходы на положительных fixture с низким false-positive rate на отрицательных; если реальный клип не содержит переходов, `0` — допустимый правильный ответ.
- **Depends:** F7.01, F7.03.

### F8.02 — Визуальные действия и связное русское описание [P1]
- [ ] Отличать change/cut detectors от подтверждённых entity/action events, хранить temporal order и повторное появление сущностей.
- [ ] Дать Qwen grounded scene sequence, а не только `image_change`; проверить связность, фактологичность, таймкоды и отсутствие вымышленных мотивов.
- [ ] Оценить 20–90-с последовательности, повторяемость generic captions и hallucinations по независимым меткам.
- **DoD:** примеры с явными visual facts/action changes, русские L3 и provenance; сравнение с baseline и ручной error taxonomy.
- **Depends:** F7.02, F7.03.

## F9 — Live CPU и архитектурный выбор

### F9.01 — Устранить 1x live lag и shared-prefetch drops [P0]
- [ ] Воспроизвести 60s 1x live cold-cache на **уникальном** источнике, CPU 4 threads или задокументированном hardware, с Qwen и теми же профилями; до остановки измерить C/E/R[L1–L3].
- [ ] Профилировать ingest/decode, embedding audio/video, prefetch queue, L1/L2, Qwen prefill/decode, SQLite/API; определить причину 503 shared-prefetch drops и C=41.828/60 в старом прогоне.
- [ ] Исправить bounded queue/backpressure без скрытого пропуска coverage; поддержать degrade profile с явными skipped/dropped и корректными watermarks.
- [ ] Повторить 1x sustained (затем 10/30 минут при доступном источнике), cold vs warm, pre-stop vs post-stop; 2x/5x отдельно.
- **DoD:** `RTF≤1` на sustained unique-media 1x, нерастущий lag и нет неучтённых drops **или** отчёт `not met` с точной причиной/планом. Не объявлять успех по offline 55.16/90 или warm-cache soak.
- **Depends:** можно вести параллельно F7.01–03.

### F9.02 — Архитектурный quality/CPU decision [P1]
- [ ] Сопоставить baseline frozen, улучшенный frozen, и при необходимости специализированные локальные CPU perception модели; не менять EmbeddingGemma 2/Qwen3-0.6B без контролируемого A/B и ADR.
- [ ] Только как **необязательное исследование** изучить, доступен ли корректный EmbeddingGemma→Qwen multimodal bridge (pooled vs token-level features, Qwen inputs_embeds, CPU GGUF deployment, data rights). Никакого training в этом этапе.
- [ ] Если требуется обучение, оформить **отдельный запрос на изменение требований** и получить явное одобрение владельца проекта; текущая [ADR-002](docs/adr/ADR-002-multimodal-bridge-evaluation.md) лишь Proposed.
- **DoD:** таблица quality/false claims/RU coherence/music transitions/CPU RTF/lag/RSS, решение `continue frozen | propose new ADR | blocked` с evidence.
- **Depends:** F7.04, F8.01–02, F9.01.

## Первое задание coding-агенту

**Сначала F7.01 + F7.02, параллельно подготовка F7.03.** После них — F7.04 и F9.01. Не начинай с fine-tuning, новой VLM или переписывания scheduler без диагностики.

Каждый отчёт: `task ID | status | commit | changed files | exact commands + exit codes | tests | model revisions | independent labels | quality/error metrics | CPU/RSS/lag/drops | raw artifacts | next gate`.
