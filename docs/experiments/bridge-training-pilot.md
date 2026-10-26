# F10 — пилот Multimodal AV Bridge для grounded визуально-аудиального сюжетного описания SHSD

> **Статус 26.10.2026:** design + interface validation разрешены. **Владелец условно разрешил любое перспективное обучение; запускать после technical/data/budget `GO`, без повторного запроса.** Этот документ описывает **проверяемую гипотезу**, а не доказанные результаты или уже обученную модель. [Todo F10](../../Todo.md) · [ADR-002](../adr/ADR-002-multimodal-bridge-evaluation.md) · [общий evaluation](av-bridge-evaluation-protocol.md).

## 1. Проверяемая цель

F10 проверяет не музыкальный классификатор, а **мультимодальный AV grounding bridge**: изображение и временная последовательность видео плюс аудио → grounded events/claims → связный русский narration через Qwen3-0.6B. Визуальный сюжет, аудиосцена и временная AV-сшивка — равноправные цели. Подробный исполняемый training recipe с IMAGE/VIDEO/AUDIO/AV режимами, samples, masks, loss и sampling зафиксирован в [F10 multimodal design](F10-multimodal-training-design.md). Система должна различать:

- что видно, какие объекты/люди остаются теми же и **что именно они делают** во времени;
- музыку, речь, шумы и наложения; инструменты/слои только при наличии различимых признаков;
- начало/исчезновение/смену музыкальных слоёв, энергию и ритмические изменения;
- порядок и совместность AV событий без выдумывания причинности, намерений, инструментов и диалогов;
- отсутствие или неопределённость evidence.

**Deployment остаётся offline CPU-only.** GPU может использоваться для обоснованного R&D training после documented `GO`, не в целевом runtime. Возможное железо для оценки ресурсов (уточнить фактическое наличие): CPU Ryzen 9 9900X3D, 2× RTX 5080 для training. Не приписывать им непроверенную производительность.

## 2. Архитектурные гипотезы

- IMAGE: один кадр → видимые сущности, атрибуты и пространственные отношения.
- VIDEO: упорядоченные кадры с исходными PTS → устойчивые entity IDs, действия, взаимодействия и порядок событий.
- AUDIO: окно звука → речь, музыка, окружение, overlap и подтверждённые слои/переходы.
- AV: синхронные аудио и видео claims → совместное grounded описание без неподтверждённой причинности.

F10.01 confirmed that EmbeddingGemma 2 exposes pre-pooling token sequences for IMAGE/VIDEO/AUDIO/AV and that the pinned llama.cpp CPU C API accepts an external Qwen prefix. The production `EmbeddingProvider` exposes opt-in sequence methods with masks, token IDs and sampled source PTS; the CPU fixture smoke is [`production_sequence_smoke.json`](../../benchmarks/reports/bridge_f10/production_sequence_smoke.json). `AVFeatureBatch` now keeps one IMAGE sequence per sampled source PTS and a separate AUDIO interval, avoiding an unproven split of flattened VIDEO tokens. It is not yet connected to `analyze` or EventGraph/B0, which still consumes pooled-path timeline claims. Two small projector/resamplers can map modality-specific token streams to Qwen's 1024-wide input; temporal fusion must carry source PTS. Claim/evidence verification and event memory remain separate components. See the [capability matrix](../../benchmarks/reports/bridge_f10/capability_matrix.md) and executable [F10 multimodal design](F10-multimodal-training-design.md).

Transport is verified, but a trained bridge is not implemented: random probe values prove no useful conditioning. F10.03 remains NO-GO until independently labeled evaluation, licensed source-separated training splits and bounded cost/stop criteria are recorded.

**Критические неопределённости:**
1. **Provider API and safe frame grouping exist:** sequence records retain token masks/IDs and source PTS; `AVFeatureBatch` holds one feature sequence per IMAGE PTS. This is only a typed adapter: no EventGraph/B0/default-analyze integration or end-to-end inference smoke has been performed. Flattened VIDEO token-to-frame spans and per-audio-token PTS remain unavailable.
2. **API answer from F10.01:** pinned Qwen3 GGUF on CPU accepts external 1024-wide token embeddings through llama.cpp `llama_batch.embd`, followed by normal text and decode. The probe uses untrained values and therefore establishes transport, not conditioning quality; integrated prefill/RSS and 1x live performance remain open.
3. Можно ли в sustained live потоке сохранить приемлемый CPU prefill/decode/RSS и 1x cadence при этой длине prefix? Нужен измеренный end-to-end прогон; одиночный API smoke на это не отвечает.
4. Достаточны ли маленький projector и frozen Qwen для обучения мультимодального языка? Это гипотеза. Если не обучается, рассмотреть B2 LoRA или более глубокое обучение после evidence первого пилота и отдельного bounded budget gate или C готовую pretrained AV модель.
5. Как получить легальные, разнообразные AV→RU training targets с независимыми источниками и без утечки в evaluation? Teacher-generated captions **не** ground truth.

## 2.1. Контроль для обучаемого моста

B0: grounded temporal event graph → текстовый Qwen3-0.6B. B1: тот же evidence + обучаемый projector/resampler → Qwen. Сравнивать на одинаковых источниках и независимых метках, чтобы не спутать новые perception facts с эффектом bridge. Pooled-only — контроль, а не гарантия деталей. API smoke passed; bridge quality remains unmeasured. Исполняемое задание: [F10 handoff](F10-agent-handoff.md), [GO template](F10-GO.template.md).

## 3. Этапы с stop/go

### F10.01 — API и latency smoke tests (разрешено)

- Проверить model cards/версии/лицензии, encoder output modalities, sequence vs pooled, timestamps; измерить shape, число токенов на 5с audio + sampled video, стоимость encoder CPU.
- Проверить Qwen inputs_embeds и output semantics с synthetic embeddings **без обучения**; измерить CPU prefill/decode, RAM, возможность GGUF deployment.
- Создать `capability_matrix.md` и маленькие воспроизводимые тесты. **No-go**, если нет поддерживаемого интерфейса или токены/время теряются без альтернативы.

### F10.02 — Спецификация обучения и данных (разрешено без сбора training corpus)

- **Design completed:** use [F10-multimodal-training-design.md](F10-multimodal-training-design.md) as the primary tensor/data/loss/training recipe. It defines IMAGE (single-frame entities/relations), VIDEO (ordered PTS, identity/actions/order), AUDIO (speech/music/ambience/layers/transitions) and synchronized AV; separate vision/audio projectors and temporal fusion; structured evidence targets + Russian caption; missing-modality masks; target-only CE; source-separated splits; negative controls; per-mode evaluation.
- **Still open:** connect the provider sequence features and source PTS to a typed evidence graph; add visual entity/action and music-layer nodes; prove token/frame alignment; build an independent per-mode evaluator and human labels; document licensed source-separated splits and bounded budget/stop criteria. F7.03 labels must not be reused for training or tuning.
- **Still open:** verify licensed source-separated train/val/held-out availability, freeze baseline and per-mode success criteria, set bounded budget/checkpoints/stop rules, and fill `benchmarks/reports/bridge_f10/F10-GO.md`. No GPU training before evidence-backed `GO`; owner authorization is already recorded and is not a blocker.

### F10.03 — Adapter-only training (разрешён после technical GO)

- Учить только B1 projector/resampler, заморозив EmbeddingGemma 2 и Qwen3-0.6B; проверять законность данных и checkpoint provenance.
- Сравнить small pooled baseline с token-level/time-aware variant **только если реально поддерживаются**.
- Записывать train/val curves, seed, optimizer, device/VRAM, data manifest и latency; не подгонять по held-out.

### F10.04 — Ablations и B2 (разрешён после evidence пилота)

- **No audio / no video / swapped audio / shuffled time / music+speech / conversation-only / image cut without action / unseen source.**
- Сравнить B1 и, если есть доказанная перспектива, B2 (adapter + минимальный LoRA) или другие методы (encoder/LLM fine-tuning, distillation) по отдельному bounded budget gate. LoRA не включать автоматически.
- Измерять precision/recall/abstain по подтверждённым music/instrument/action/transition claims; factuality, hallucinations, русскую сюжетную связность, omission, число generic captions, latency и CPU memory.

### F10.05 — CPU deployment decision (после обучения, если разрешено)

- A0 (текущий frozen), A2 (улучшенный frozen), B1, B2 (если разрешён), C (готовая pretrained альтернатива) сравнить на одинаковых independent clips и 1x live unique-media cold-cache.
- Отдельно проверить adapter load, quantization, KV/prefix cache, model warm-up, bounded ring/queues, C/E/R lag p50/p95/slope, drops, Qwen prefill/decode и process-tree RSS.
- Решение: `ship frozen | ship bridge | ship specialized perception | no-go`. **Не** выбирать bridge только потому, что train loss упал.

## 4. Измерения и критерии

| Критерий | Что сравнивать |
|---|---|
| Русский сюжет | Содержательные действия, идентичность сущностей, временной порядок, связность без неподтверждённых мотивов |
| Музыкальная детализация | Music premise отдельно от percussion/bass/vocals/instrument; onset/offset/semantic transition accuracy |
| Factual grounding | False premises, unsupported claims, source/time/evidence provenance, выраженные/пропущенные L2 claims |
| Robustness | Unseen source, missing modality, swapped-audio, shuffled-time, speech-only, ambience-only |
| CPU performance | Sustained 1x, cold-cache, C/E/R coverage, lag slope, drops, RTF, CPU threads, RAM/RSS, Qwen tok/s |
| Model viability | Official license, encoder tokens, Qwen embedding API, GGUF/llama.cpp compatibility, adapter quantization |

Никаких заранее придуманных «+X% качества» и «Y ms overhead» без замеров. Утвердить целевые thresholds **до** обучения, затем публиковать actuals и confidence intervals с `N`.

## 5. Артефакты

`benchmarks/reports/bridge_f10/`:
- `capability_matrix.md` — ссылки на upstream API, результаты smoke tests, версии и точные команды;
- `data_manifest.json` — лицензии, splits, source IDs, предотвращение leakage (после technical/data `GO`);
- `train_manifest.json` + checkpoints metadata (после technical/data `GO`);
- `eval_per_interval.jsonl`, `ablation_results.json`, `cpu_live_report.json`, `decision.md`.

**Next coding work:** continue F10.02 alongside F7.03/F9.01: (1) add independently supported visual entity/action and music-layer nodes to EventGraph; (2) connect `AVFeatureBatch` to B0 and verify full PTS/evidence flow; (3) build the per-mode evaluator and same-source A0/B0 comparison; (4) obtain independent labels and confirm rights for source-separated train/val/held-out sets; (5) set a real GPU-hours/VRAM budget and numeric success thresholds. Current evidence-backed **NO-GO** and missing prerequisites are recorded in [`F10-GO.md`](../../benchmarks/reports/bridge_f10/F10-GO.md). No bridge training until those items are resolved.


## Условное разрешение на R&D обучение — 26.10.2026

Владелец разрешил **любое обучение, если оно перспективно поможет решить главную боль**: содержательный, достоверный визуальный сюжет, подробные музыкальные слои/переходы и устойчивый CPU-only offline realtime. Это включает adapter/projector, LoRA, encoder/LLM fine-tuning, distillation и альтернативные модели. **Повторного согласования каждого эксперимента не требуется.**

**До GPU training:** (1) подтверждённый interface/conditioning и правдоподобный CPU deploy path; (2) права на данные и source-separated train/val/held-out; (3) зафиксированный baseline и независимые quality metrics; (4) bounded GPU budget, checkpoints и stop conditions; (5) письменный `F10-GO.md` с результатом `GO`. Если что-то не выполнено — `NO-GO`, не скрывать риск. После короткого пилота продолжать лишь при измеренном улучшении без роста ложных утверждений. В production новые веса попадут только после held-out A/B и sustained 1x CPU live. Это разрешение на исследование, **не доказательство, что обучение обязательно поможет**.


## Точный рецепт для coding-агента

Выполнять [F10-multimodal-training-design.md](F10-multimodal-training-design.md): IMAGE — одно изображение и отношения объектов, VIDEO — временная последовательность кадров/сюжет, AUDIO — инструменты/музыкальные слои, AV — общая синхронизированная история. Там определены формы входов и выходов, source-separated JSONL, два адаптера vision/audio, маски отсутствующих модальностей, loss на целевых токенах JSON и русского описания, стартовый optimizer и критерии CPU realtime. Это гипотеза разработки до измерений, не готовая обученная модель.
