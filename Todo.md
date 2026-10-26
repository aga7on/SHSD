# Todo.md — SHSD: активный backlog качества и realtime

> **Версия 0.7 · 27.10.2026.** Все новые задачи ниже **открыты** до предъявления воспроизводимых доказательств. Прежний F0–F6 чеклист (исторически 157/159) [архивирован без изменений](docs/archive/2026-10-26-pre-multimodal-review/Todo.md). Эта цифра не измеряет готовность продукта.
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
- [x] Проверить `src/shsd/semantic/temporal.py::_music_scene_supports_details`, `analyze.py` и текущие hypothesis configs. Сохранить исходный baseline и повторить `Tears of Steel`; см. [`real_video_quality_review.md`](benchmarks/reports/music_quality_v2/real_video_quality_review.md).
- [x] Сохранить возможность **внутреннего** coarse-to-fine поиска при `music_possible`, но **не публиковать** детали без отдельно подтверждённой музыкальной предпосылки и собственного evidence по оси. На 01:10–01:25 ударные получили `exploratory_support`, публикация подавлена.
- [x] Учесть наложение речи и фоновой музыки: conversation-dominant не считается music-absent; подтверждённые music+speech детали проходят независимый premise/evidence gate.
- [x] Явно сохранять premise state и provenance в claim/event; старый JSONL остаётся читаемым при отсутствующих полях.
- [x] Регрессии: conversation-only hard negative; music-only; music+speech; uncertain music; conflicting top/runner-up; реальный интервал 01:10–01:25. `python -m pytest tests\\unit\\test_temporal_semantic.py tests\\unit\\test_memory.py -q` — 27 passed; реальный прогон — в F7.01 отчёте.
- **DoD:** технические условия выполнены: опубликованные детали требуют подтверждённой музыкальной предпосылки и собственного evidence; overlap покрыт тестами; реальный прогон не публикует runner-up-only percussion. Точность на независимых human labels остаётся в F7.03.
- **Depends:** baseline `20acb747`.

### F7.02 — Исправить L2→L3 claim accounting и фактическое покрытие [P0]
- [x] Проверить `src/shsd/captions/narrator.py`: `used_claim_ids` раньше перечислял все входы и не отражал фактическое покрытие.
- [x] Развести `input_claim_ids`, `expressed_claim_ids`, `omitted_claim_ids` и `uncertain_claim_ids`; добавить проверяемую source-overlap политику с coverage score без автоматического присвоения всех входных IDs.
- [x] Ставить подтверждённые L2 музыкальные детали выше общей сцены в narrator input; остальные принятые утверждения и осознанные пропуски сохраняются отдельно.
- [x] Проверять unsupported слова, отрицания и clause-to-source grounding, а не только общий словарь; fallback сохраняет точные claims и ASR-цитаты. Применяется к audio/video claims.
- [x] Регрессия: 01:10–01:25 Qwen говорит только о разговоре; percussion и две cross-modal связи перечислены как omitted, не как expressed. Unit negative case покрывает разговор + percussion.
- **DoD:** выходная схема, UI/API/JSONL и Markdown export согласованы; omission измерим; `used_claim_ids` совпадает с выраженными; unit/regression команда и полный реальный прогон отражены в [`real_video_quality_review.md`](benchmarks/reports/music_quality_v2/real_video_quality_review.md). Coverage — консервативная текстовая эвристика, не NLI; независимая ручная оценка остаётся в F7.03.
- [x] 90s L1/L2/L3 audit with integrated B0 graph: 62 L1 + 62 L2 events, 3 captions; 100 window matches (95 `uncertain`, 5 accepted); L2 had 11 abstained, 1 confirmed, 50 skipped, and zero newly accepted details or semantic transitions. One generated caption substantively describes dialogue; two are safe temporal-coincidence fallbacks. The graph contains 62 claim-event nodes and 61 start-order edges, with no causal edges. See [review](benchmarks/reports/music_quality_v2/real_video_quality_review_b0_graph.md), [JSONL](benchmarks/reports/music_quality_v2/f701_real_tos_l3_b0_graph.jsonl), and [diagnostic](benchmarks/reports/semantic_matcher_diagnostic_20261026/semantic_matcher_diagnostic.md). This run reused cached audio and image embeddings and took 27.91s; it is offline and not realtime. A prior cache-stable reference pass took 50.56s with 2/8 image cache hits.
- **Depends:** F7.01 для publishable claims.

### F7.03 — Независимые ручные метки и слепая оценка [P0]
- **Текущий label status:** `benchmarks/review/iterative_speech_presence_natural/review_key/answer_key.csv` содержит 40 source-description-derived интервалов, а не независимо прослушанные метки; README набора прямо отмечает это ограничение. В label-free диагностиках использовать эти строки как ground truth запрещено. Отдельный CSV независимой оценки ещё не поступил.
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

## F10 — Multimodal AV Bridge для визуально-аудиального сюжетного описания

**Первый результат агента — исполняемый код и измерения, а не очередной ресерч.** Порядок коммитов, критерии и негативные тесты — [handoff](docs/experiments/F10-agent-handoff.md).

> **Не откладывать F10.01–02 до F9.** Они идут параллельно P0. **Обучение условно одобрено владельцем**: F10.03 готов к запуску после feasibility/data/budget `GO`; F10.04 — после evidence первого пилота; F10.05 — после quality/CPU сравнения. Это конкретный план пилота, не обязательство менять production.

### F10.01 — Проверка реальных интерфейсов и ограничений [P1; можно сейчас]
- [x] EmbeddingGemma 2: IMAGE/AUDIO/VIDEO/AV pooled vectors, pre-pooling token shapes, masks, frame PTS/timestamp markers and CPU single-call times verified in [`api_smoke.json`](benchmarks/reports/bridge_f10/api_smoke.json).
- [x] Qwen3-0.6B: synthetic Transformers `inputs_embeds` forward/gradient/generate and the actual pinned Q8_0 GGUF on CPU with a `[4,1024]` external prefix followed by text/decode verified in [`llama_cpp_prefix_smoke.json`](benchmarks/reports/bridge_f10/llama_cpp_prefix_smoke.json). Plain text smoke: [`qwen_text_smoke.json`](benchmarks/reports/bridge_f10/qwen_text_smoke.json).
- [x] Model/runtime revisions and local artifact hashes checked; pinned model metadata records EmbeddingGemma Apache-2.0, Qwen Apache-2.0 and llama.cpp MIT. This is not an estimate of GPU training cost.
- [x] Added offline API probes and [`capability_matrix.md`](benchmarks/reports/bridge_f10/capability_matrix.md). The matrix distinguishes API feasibility from learned quality and sustained 1x performance.
- [x] Expose opt-in sequence features and source PTS through the production `EmbeddingProvider`: `encode_frame_features`, `encode_audio_features`, `encode_video_features`, `encode_joint_features`; real local CPU smoke covers all four modes in [`production_sequence_smoke.json`](benchmarks/reports/bridge_f10/production_sequence_smoke.json). The main `analyze` route still uses pooled features pending EventGraph/B0 integration.
- [ ] Confirm stable streaming cadence/RSS and B1 quality after a bounded, licensed, source-separated data/evaluation plan.
- **DoD:** technical custom-prefix path is `GO`; B1 training remains `NO-GO` until F10.02 has independent labels, licensed train/val/held-out data, a baseline, bounded budget and stop criteria. Four-second CPU video/AV single calls are not a 1x stream claim.
- **Depends:** API feasibility complete; continue F7.01–03 and F10.02 in parallel.

### F10.02 — Реализация B0 и независимая оценка [P0; дизайн уже готов]
- [x] Переформулировать F10 как **Multimodal AV Bridge** с равными целями для визуального сюжета, звуковой сцены, временной AV-сшивки и grounded русского narration.
- [x] Зафиксировать исполняемый B1 tensor/data/loss design для IMAGE, VIDEO, AUDIO и AV: две modality ветки, PTS/time features, missing-modality masks, structured claims + `caption_ru`, target-only loss, negatives и per-mode metrics — [спецификация](docs/experiments/F10-multimodal-training-design.md).
- [x] Описать B0 baseline, B1 frozen encoder/Qwen + trainable projector/resampler, B2 только после перспективы B1 и вариант C; конкретный контроль и stop/go — [pilot protocol](docs/experiments/bridge-training-pilot.md).
- [x] Добавить production-provider методы для sequence features, masks, token IDs и source PTS; подтвердить IMAGE/VIDEO/AUDIO/AV на реальном CPU fixture — [`production_sequence_smoke.json`](benchmarks/reports/bridge_f10/production_sequence_smoke.json).
- [x] Add a typed temporal claim graph and route it into B0 narration requests; JSONL now emits `event_graph` with source evidence, revisions, confidence type, and start-order edges: [graph.py](src/shsd/memory/graph.py).
- [x] Define IMAGE/VIDEO/AUDIO/AV sample JSON Schema and implement a JSONL validator for PTS/evidence references, modality masks, license-permitted split use, human verification, and source-group leakage: [schema](configs/schemas/av_bridge_sample_v1.schema.json), [validator](scripts/validate_bridge_dataset.py).
- [x] Add an alignment-safe `AVFeatureBatch` adapter that retains one unpooled IMAGE sequence per exact frame PTS and an independent interval AUDIO sequence: [features.py](src/shsd/bridge/features.py).
- [x] Add unit tests for `dataset.py`, `AVFeatureBatch`, EventGraph links, action-scan windows, raw pixel-change summaries, blind-review CSV validation, and human-reviewed B0 conversion: modality masks, PTS evidence and offset integrity, annotation provenance, EAO fields, transition bracketing, Qwen-request rehydration, and narration output plumbing; the eight F10 bridge/review modules → **75 passed**, full `tests/unit` → **274 passed**; Ruff clean. See [bridge tests](tests/unit/test_bridge_dataset.py), [graph tests](tests/unit/test_event_graph.py), [review validator tests](tests/unit/test_validate_f10_review_labels.py), [reviewed graph tests](tests/unit/test_build_f10_reviewed_graphs.py), and [memory tests](tests/unit/test_memory.py).
- [x] Validate train/val/test manifests together; reject split-field mismatches, duplicate sample IDs, and cross-split collisions in `source_group_id`, `source_id`, or `source_sha256`; support `--train`, `--val`, `--test` in the CLI.
- [x] Connect ordered `AVFeatureBatch` frame sequences through the B0 `GroundedEventGraph`; test PTS offset, per-frame token shapes, source/epoch matching, event-to-frame references, and explicit no-action-inference. The optional graph can retain unverified model hypotheses separately. The offline importer turns only `human_verified` review rows into accepted, provenance-tagged visual-action/music-transition claims, links visual claims to exact sequence frame refs, and can run pinned CPU Qwen with `--narrate-qwen` to save actual L3 results with coverage/fallback metadata: [builder](scripts/build_f10_reviewed_graphs.py). Builder integration tests use synthetic rows only; no real output is considered verified.
- [ ] **P0 — Visual semantic grounding:** replace or constrain the external action baseline before treating it as B0 evidence. In a 13-window scan it ranked “rises from bed” in 12 windows, including late frames with little pixel change; the logit rose to 12.984 as mean frame difference fell. Keep hypotheses unverified and outside Qwen/default `analyze`; obtain independent labels before accepting entity/action/object events. See [scan JSON](benchmarks/reports/bridge_f10/video_action_sequence_xclip_tears120-140.json) and [semantic candidates report](benchmarks/reports/bridge_f10/f10_03_semantic_candidates_20261027.md).
- [ ] **P0 — Reproducible examples:** obtain independent VIDEO and AUDIO labels, validate source-time boundaries/evidence PTS, then run the reviewed B0 builder and compare its Qwen text with the labels. The 90-second real-film L1/L2/L3 output has no independent labels, no accepted new L2 music detail, and no natural music-layer transition description. The audio-only L1/L2/L3 output identifies conversation after source PTS 190000 ms and abstains on music detail. Review packet: [manifest](benchmarks/review/bridge_f10_examples/review_manifest.json), [guide](benchmarks/review/bridge_f10_examples/review_guide.md), [CSV template](benchmarks/review/bridge_f10_examples/human_labels_template.csv), [validator](scripts/validate_f10_review_labels.py), [B0 importer](scripts/build_f10_reviewed_graphs.py).
- [ ] **P1 — CPU budget:** after the semantic examples, reduce total CPU live lag with Qwen enabled. A current 27.10 cold-cache 60s run captured 41.818s (0.697 capture/wall ratio), embedded 35.099s (0.585), produced 13 L2 revisions and 2 Qwen captions before stop, had 548 shared-prefetch drops, median live caption lag 20.76s, and 3.43GB peak process-tree RSS. It does not meet 1x; full stage/worker metrics are in the [follow-up report](benchmarks/reports/bridge_f10/f10_02_followup_20261027.md). Exclude post-stop drain from realtime figures.
- [ ] Независимо разметить evaluation set F7.03; отдельно подтвердить лицензированные source-separated train/val/held-out источники. F7.03 labels не использовать для обучения или tuning.
- [x] Record the current evidence-backed B1 decision as **NO-GO**, with API/B0 limits and the exact data, labels, and budget blockers: [`F10-GO.md`](benchmarks/reports/bridge_f10/F10-GO.md). This is not approval to start training.
- [ ] Unblock the GO gate with rights-cleared source-separated data, independent per-mode human labels, frozen thresholds, verified GPU-hours/VRAM budget, and a same-source A0/B0 evaluation.
- **DoD:** дизайн закрыт ссылками выше; технический/data/budget `GO` — только после production feature/PTS path, B0 baseline, независимой оценки, прав на отдельные train/val/held-out sources, bounded budget и заранее зарегистрированных per-mode criteria. До этого training = `NO-GO`; повторно спрашивать владельца разрешение не нужно.
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

**Параллельные потоки:** (A) F7.03 независимая ручная оценка и F9.01 live backlog; (B) F10.02 production token/PTS path, typed EventGraph/B0 и независимый evaluator. Дизайн обучения IMAGE/VIDEO/AUDIO/AV уже записан в [multimodal training design](docs/experiments/F10-multimodal-training-design.md). B1 training запускать после technical/data/budget `GO`, без повторного разрешения; LoRA/другое обучение — только после подтверждённой перспективы B1. Затем сравнить A0/A2/B1/C по одному протоколу.

Каждый отчёт: `task ID | status | commit | changed files | exact commands + exit codes | tests | model revisions | independent labels | quality/error metrics | CPU/RSS/lag/drops | raw artifacts | next gate`.


## Условное разрешение на R&D обучение — 26.10.2026

Владелец разрешил **любое обучение, если оно перспективно поможет решить главную боль**: содержательный, достоверный визуальный сюжет, подробные музыкальные слои/переходы и устойчивый CPU-only offline realtime. Это включает adapter/projector, LoRA, encoder/LLM fine-tuning, distillation и альтернативные модели. **Повторного согласования каждого эксперимента не требуется.**

**До GPU training:** (1) подтверждённый interface/conditioning и правдоподобный CPU deploy path; (2) права на данные и source-separated train/val/held-out; (3) зафиксированный baseline и независимые quality metrics; (4) bounded GPU budget, checkpoints и stop conditions; (5) письменный `F10-GO.md` с результатом `GO`. Если что-то не выполнено — `NO-GO`, не скрывать риск. После короткого пилота продолжать лишь при измеренном улучшении без роста ложных утверждений. В production новые веса попадут только после held-out A/B и sustained 1x CPU live. Это разрешение на исследование, **не доказательство, что обучение обязательно поможет**.

F10 — не музыкальный классификатор и не музыкальный fine-tuning. Цель — визуальные сущности, действия и порядок, аудиосцена и музыкальные слои, их grounded временная сшивка и связный русский narration.

## F10 — ближайшие четыре коммита агента

1. **A:** encoder/Qwen conditioning/CPU smoke tests, capability matrix с exact commands.
2. **B:** grounded event graph, B0 text-only Qwen baseline, human-labeled independent eval, заполненный F10-GO.
3. **C (после GO):** короткий B1 projector training pilot с train/val/held-out, ablations, quality A/B и CPU measurements.
4. **D:** сравнение B0/B1/специализированных perception моделей, sustained 1x live и решение о production. LoRA/другой fine-tune только при измеренном сигнале перспективности.

Полный контракт: [F10 handoff](docs/experiments/F10-agent-handoff.md).


## F10.06 — Обучаемый AV bridge: IMAGE, VIDEO, AUDIO и AV равноправны [P0]

**Обязательная исполняемая спецификация: [F10-multimodal-training-design.md](docs/experiments/F10-multimodal-training-design.md).** Предыдущее F10 описывало архитектуру, но не loss, JSONL, masks и training schedule. Новый документ — первичный для деталей обучения. Музыка не может заменить выполнение задач по видео/изображениям.

- [ ] IMAGE-only: одиночное изображение, entities/attributes/spatial relations, grounded русский текст; отрицательный тест на придуманные движения/звуки.
- [ ] VIDEO-only: **упорядоченные кадры с PTS**, entity tracking, subject-action-object, temporal before/after, shuffled frames negatives и связный русский сюжет; frame tags недостаточно.
- [ ] AUDIO-only: speech/music/ambience overlap, инструменты/бас/ударные/вокал, музыкальные слои, onset/offset, не выдумывать видимых людей.
- [ ] AV: синхронизированная визуальная последовательность + музыка/звук с timestamp evidence; shifted/swapped-audio negatives и отсутствие ложной причинности.
- [ ] Реализовать `FeatureBatch`, two-branch vision/audio projector+temporal resampler, missing modality masks, source-separated JSONL, grounded events+caption target, Qwen target-only CE с `labels=-100` для prefix/prompt/pad и macro-balanced four-mode evaluation.
- [ ] B1: frozen EmbeddingGemma 2 и Qwen3-0.6B, bridge-only AdamW (initial lr=1e-4 и остальные гиперпараметры в design, **не validated**), короткий train-only sanity, bounded pilot только после documented GO; LoRA при необходимости.
- [ ] Held-out quality отдельно для IMAGE, VIDEO, AUDIO и AV, hallucinations/unsupported claims и cold unique-media CPU 1x lag/drops.
- **DoD:** реальный код/tests, source/rights/training config, независимая ручная разметка и raw сравнение A0/B0/B1. **Music-only improvement при визуальном провале = NO-GO.**

**Сразу агенту:** PR1 проверка API и feature shapes для image/video/audio и CPU Qwen; PR2 JSONL/data/masks/EventGraph/B0; PR3 B1 training после GO; PR4 per-mode A/B+CPU realtime. [Поручение](docs/experiments/F10-agent-handoff.md).
