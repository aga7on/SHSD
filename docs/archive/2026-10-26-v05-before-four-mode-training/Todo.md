# Todo.md — SHSD: активный backlog качества и realtime

> **Версия 0.5 · 26.10.2026.** Все новые задачи ниже **открыты** до предъявления воспроизводимых доказательств. Прежний F0–F6 чеклист (исторически 157/159) [архивирован без изменений](docs/archive/2026-10-26-pre-multimodal-review/Todo.md). Эта цифра не измеряет готовность продукта.
>
> **Исполняемое ТЗ:** [F10-agent-handoff.md](docs/experiments/F10-agent-handoff.md) · [F10-GO template](docs/experiments/F10-GO.template.md).
>
> Цель: [Workspace.md](Workspace.md); правила агента: [Agents.md](Agents.md); протокол: [docs/experiments/av-bridge-evaluation-protocol.md](docs/experiments/av-bridge-evaluation-protocol.md).

## Обязательные правила

- **P0** — достоверность, traceability, оценка качества и live-блокеры; **P1** — детализация; **P2** — исследование альтернатив.
- CPU-only/offline production; EmbeddingGemma 2 + Qwen3-0.6B сохраняются. **F10 — параллельный исследовательский трек обучаемого моста**. Capability audit и проектирование можно делать сейчас; владелец уже разрешил любое перспективное обучение; training/projector/LoRA и подготовка законного обучающего корпуса — после documented feasibility/data/budget `GO` и без повторного разрешения.
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
- [ ] Использовать результаты **параллельного F10**: проверить EmbeddingGemma→Qwen bridge (pooled vs token-level, Qwen inputs_embeds, CPU GGUF deployment, data rights) и сравнить с frozen на независимых метках. Training-этап F10 запускать после технического `GO` по уже полученному разрешению.
- [ ] Если требуется обучение, применить уже полученное **условное разрешение владельца** по принятой [ADR-002](docs/adr/ADR-002-multimodal-bridge-evaluation.md); отдельный запрос не нужен, но технический `GO` обязателен.
- **DoD:** таблица quality/false claims/RU coherence/music transitions/CPU RTF/lag/RSS, решение `continue frozen | propose new ADR | blocked` с evidence.
- **Depends:** F7.04, F8.01–02, F9.01 и результаты F10.01–02; обученный вариант — только при одобренных F10.03–05.

## F10 — Обучаемый мультимодальный мост: параллельный R&D-трек

**Первый результат агента — исполняемый код и измерения, а не очередной ресерч.** Порядок коммитов, критерии и негативные тесты — [handoff](docs/experiments/F10-agent-handoff.md).

> **Не откладывать F10.01–02 до F9.** Они идут параллельно P0. **Обучение условно одобрено владельцем**: F10.03 готов к запуску после feasibility/data/budget `GO`; F10.04 — после evidence первого пилота; F10.05 — после quality/CPU сравнения. Это конкретный план пилота, не обязательство менять production.

### F10.01 — Проверка реальных интерфейсов и ограничений [P1; можно сейчас]
- [ ] По официальным model cards и **исполняемым smoke tests** выяснить, какие EmbeddingGemma 2 outputs доступны: pooled, patch/token/time-level features, отдельные audio/video paths, timestamps, нормализация и возможность получить sequence representations без неподдерживаемых API.
- [ ] Проверить, принимает ли конкретная Qwen3-0.6B implementation `inputs_embeds`/prefix tokens и как это соотносится с CPU GGUF/llama.cpp; сравнить PyTorch prototype и целевой runtime. Записать размерности, порядок модальностей, masking и стоимость prefill.
- [ ] Проверить лицензии, совместимость версий и ограничения аппаратуры для отдельного GPU-training и **CPU-only** запуска. Не обещать, что pooled 768d восстанавливает действия, инструменты или временные связи.
- [ ] Добавить исполняемые shape/API/CPU smoke tests, raw outputs и capability_matrix.md; не выдавать текстовый prompt за multimodal prefix.
- **DoD:** таблица `supported/unsupported/unknown`, минимальные воспроизводимые smoke tests и `go/no-go` для непрерывного multimodal prefix. Не выдавать fake soft prompt за работающий bridge.
- **Depends:** нет; стартовать параллельно F7.01–03.

### F10.02 — Дизайн пилота и независимой оценки [P1; можно сейчас]
- [ ] Зафиксировать варианты B1: frozen encoder+frozen Qwen+малый projector/resampler; B2: B1+ограниченный LoRA **только если B1 недостаточен**; альтернативу C с компактной pretrained AV/audio perception моделью.
- [ ] Спроектировать token-level/temporal audio/video conditioning и fusion: 1) что видно и как меняется, 2) какие звуковые/музыкальные слои слышны, 3) что произошло раньше/позже, 4) какие утверждения имеют evidence.
- [ ] Согласовать законные train/val/test источники **без source leakage**; training data собирать после проверки лицензий и source-separated splits. Разметка F7.03 — только evaluation, не скрытый train set.
- [ ] Утвердить cost/quality metrics и ablations: audio-only, video-only, AV, swapped-audio, shuffled-time, missing modality, negative prompts, 1x cold-cache live, memory, CPU tok/s и prefill.
- [ ] Реализовать B0 typed event graph→Qwen и независимый eval runner (visual actions, music transitions, input/expressed/omitted claims).
- [ ] Заполнить [GO template](docs/experiments/F10-GO.template.md) реальными доказательствами в benchmarks/reports/bridge_f10/F10-GO.md.
- **DoD:** [bridge pilot protocol](docs/experiments/bridge-training-pilot.md), явные критерии остановки, сравнение с frozen A0/A2 и documented technical/data/budget `GO` по уже полученному разрешению.
- **Depends:** F10.01 и схема F7.03; F7–F9 продолжаются параллельно.

### F10.03 — Минимальный projector-only training pilot [P1; разрешено после technical GO]
- [ ] **После documented technical/data/budget `GO`**: подготовить лицензированные paired AV→RU event/caption train/val источники, не смешивая их с held-out test.
- [ ] Обучать только малый bridge/resampler при замороженных EmbeddingGemma 2 и Qwen3-0.6B; фиксировать reproducibility, GPU hardware/VRAM, loss, training wall time и checkpoint lineage.
- [ ] Вывести строго одинаковые outputs и provenance для frozen A и B1; не считать teacher-generated псевдофакты ground truth.
- **DoD:** reproducible checkpoint, контроль утечки и честный held-out результат; при неподдерживаемом CPU deployment — `no-go`.
- **Depends:** F10.01–02 и успешный technical/data/budget `GO`; повторное разрешение не требуется.

### F10.04 — Controlled ablation и при необходимости LoRA [P2; разрешено после evidence первого пилота]
- [ ] Сравнить B1 с B2 (LoRA или другой метод обучения при доказанной перспективности) и A2/C на одинаковых клипах. Ablations: pooled vs sequence features, temporal order, AV alignment, music+speech, visual actions, unknown/hard negatives.
- [ ] Отдельно измерить ложные инструменты/действия, factual story coherence, music onset/offset и semantic transitions, русский текст и CPU prefill/decode/lag.
- **DoD:** report с CI/размером выборки, ablations, failures, latency/coverage; не продвигать модель по одному субъективно удачному примеру.
- **Depends:** F10.03, независимые метки F7.03, обоснованный bounded budget для следующего эксперимента.

### F10.05 — Production decision: frozen vs bridge vs alternative [P1; после результатов]
- [ ] Сравнить A2/B1/B2/C на sustained 1x CPU с реальными watermarks и bounded queues; проверить лицензии и формат поставки.
- [ ] Принять `ship frozen | ship bridge | use specialized perception | no-go` только по quality/CPU evidence; изменение production architecture — отдельная ADR.
- **DoD:** подписанное решение с воспроизводимыми quality/live отчетами; ни один training artifact не становится runtime dependency автоматически.
- **Depends:** F7.04, F8.02, F9.01, F10.03–04 после технических `GO`.

## Первое задание coding-агенту

**Два параллельных потока:** (A) F7.01 + F7.02, разметка F7.03 и live F9.01; (B) **F10.01 + F10.02 уже сейчас** — технический аудит EmbeddingGemma 2→Qwen3-0.6B и дизайн обучаемого моста. Обучение F10.03 и законный training data запускать после technical/data/budget `GO`, без повторного разрешения; LoRA или другое обучение F10.04 — после подтверждения перспективности первого пилота. Затем сравнить A2/B1/C по одному протоколу.

Каждый отчёт: `task ID | status | commit | changed files | exact commands + exit codes | tests | model revisions | independent labels | quality/error metrics | CPU/RSS/lag/drops | raw artifacts | next gate`.


## Условное разрешение на R&D обучение — 26.10.2026

Владелец разрешил **любое обучение, если оно перспективно поможет решить главную боль**: содержательный, достоверный визуальный сюжет, подробные музыкальные слои/переходы и устойчивый CPU-only offline realtime. Это включает adapter/projector, LoRA, encoder/LLM fine-tuning, distillation и альтернативные модели. **Повторного согласования каждого эксперимента не требуется.**

**До GPU training:** (1) подтверждённый interface/conditioning и правдоподобный CPU deploy path; (2) права на данные и source-separated train/val/held-out; (3) зафиксированный baseline и независимые quality metrics; (4) bounded GPU budget, checkpoints и stop conditions; (5) письменный `F10-GO.md` с результатом `GO`. Если что-то не выполнено — `NO-GO`, не скрывать риск. После короткого пилота продолжать лишь при измеренном улучшении без роста ложных утверждений. В production новые веса попадут только после held-out A/B и sustained 1x CPU live. Это разрешение на исследование, **не доказательство, что обучение обязательно поможет**.

## F10 — ближайшие четыре коммита агента

1. **A:** encoder/Qwen conditioning/CPU smoke tests, capability matrix с exact commands.
2. **B:** grounded event graph, B0 text-only Qwen baseline, human-labeled independent eval, заполненный F10-GO.
3. **C (после GO):** короткий B1 projector training pilot с train/val/held-out, ablations, quality A/B и CPU measurements.
4. **D:** сравнение B0/B1/специализированных perception моделей, sustained 1x live и решение о production. LoRA/другой fine-tune только при измеренном сигнале перспективности.

Полный контракт: [F10 handoff](docs/experiments/F10-agent-handoff.md).
