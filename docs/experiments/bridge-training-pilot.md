# F10 — план пилота обучаемого мультимодального моста SHSD

> **Статус 26.10.2026:** design + interface validation разрешены. **Владелец условно разрешил любое перспективное обучение; запускать после technical/data/budget `GO`, без повторного запроса.** Этот документ описывает **проверяемую гипотезу**, а не доказанные результаты или уже обученную модель. [Todo F10](../../Todo.md) · [ADR-002](../adr/ADR-002-multimodal-bridge-evaluation.md) · [общий evaluation](av-bridge-evaluation-protocol.md).

## 1. Проверяемая цель

Получать из синхронизированного аудио и видео **grounded последовательность событий** и содержательное русское описание через Qwen3-0.6B, а не просто music/video теги. Система должна различать:

- что видно, какие объекты/люди остаются теми же и **что именно они делают** во времени;
- музыку, речь, шумы и наложения; инструменты/слои только при наличии различимых признаков;
- начало/исчезновение/смену музыкальных слоёв, энергию и ритмические изменения;
- порядок и совместность AV событий без выдумывания причинности, намерений, инструментов и диалогов;
- отсутствие или неопределённость evidence.

**Deployment остаётся offline CPU-only.** GPU может использоваться для обоснованного R&D training после documented `GO`, не в целевом runtime. Возможное железо для оценки ресурсов (уточнить фактическое наличие): CPU Ryzen 9 9900X3D, 2× RTX 5080 для training. Не приписывать им непроверенную производительность.

## 2. Архитектурные гипотезы

```text
audio windows + video frames + PTS
  ├── EmbeddingGemma 2: available audio/video sequence/pooled features?
  ├── optional DSP / ASR / independent grounding evidence
  └── temporal sampler / alignment
         ↓
   small trainable projector or resampler (B1)
         ↓
   bounded multimodal prefix / equivalent conditioning
         ↓
   frozen Qwen3-0.6B -> Russian grounded AV description
         ↓
   claim/evidence verifier + temporal event memory + L3 publication
```

**Критические неопределённости:**
1. Реально ли EmbeddingGemma 2 предоставляет **token/patch/time-level** representations для аудио и видео? Если только pooled vector — точные действия, инструменты и переходы могут быть невосстановимы. Нужен shape/probe test на реальном чекпойнте.
2. Поддерживает ли конкретная реализация Qwen3-0.6B корректный **не-текстовый** conditioning (`inputs_embeds`, prefix, KV, custom token projection)? Проверить обучение и инференс, а не просто совместимость размерностей.
3. Можно ли перенести этот conditioning в **CPU llama.cpp/GGUF** без неподдерживаемого патча или тяжёлого PyTorch-only runtime? Проверить prefill, KV cache, квантование, RAM.
4. Достаточны ли маленький projector и frozen Qwen для обучения мультимодального языка? Это гипотеза. Если не обучается, рассмотреть B2 LoRA или более глубокое обучение после evidence первого пилота и отдельного bounded budget gate или C готовую pretrained AV модель.
5. Как получить легальные, разнообразные AV→RU training targets с независимыми источниками и без утечки в evaluation? Teacher-generated captions **не** ground truth.

## 2.1. Контроль для обучаемого моста

B0: grounded temporal event graph → текстовый Qwen3-0.6B. B1: тот же evidence + обучаемый projector/resampler → Qwen. Сравнивать на одинаковых источниках и независимых метках, чтобы не спутать новые perception facts с эффектом bridge. Pooled-only — контроль, а не гарантия деталей. Последний Deep Research не завершён, API проверять smoke tests. Исполняемое задание: [F10 handoff](F10-agent-handoff.md), [GO template](F10-GO.template.md).

## 3. Этапы с stop/go

### F10.01 — API и latency smoke tests (разрешено)

- Проверить model cards/версии/лицензии, encoder output modalities, sequence vs pooled, timestamps; измерить shape, число токенов на 5с audio + sampled video, стоимость encoder CPU.
- Проверить Qwen inputs_embeds и output semantics с synthetic embeddings **без обучения**; измерить CPU prefill/decode, RAM, возможность GGUF deployment.
- Создать `capability_matrix.md` и маленькие воспроизводимые тесты. **No-go**, если нет поддерживаемого интерфейса или токены/время теряются без альтернативы.

### F10.02 — Спецификация обучения и данных (разрешено без сбора training corpus)

- Спроектировать B1: frozen encoder+LLM, минимальный projector/resampler; ограниченный temporal prefix; независимый grounding/verification.
- Зафиксировать data schema: `source_id, interval_ms, modality, features_version, entity/action/music/transition annotations, caption_ru, evidence_refs, rights, split`.
- Train/val/test **source-separated**, вручную проверенный held-out и negatives; отсутствие тестовых `Tears of Steel` интервалов в training при использовании их как test.
- Предварительно выбрать budget токенов/окон, latency, критерии улучшения и условия остановки; документированный technical/data/budget `GO` до F10.03; разрешение владельца уже получено.

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

**Следующее действие coding-агента:** F10.01 в параллель с F7.01/F7.02. Перед F10.03 создать `F10-GO.md` с проверенным интерфейсом, лицензиями, source-separated splits, frozen baseline, заранее определёнными quality/CPU метриками, bounded GPU budget и stop criteria. При неуспехе — `NO-GO`; при успехе — начать обучение без повторного запроса владельца. После B1 продолжать только при измеренном прогрессе; не расходовать ресурсы безлимитно.


## Условное разрешение на R&D обучение — 26.10.2026

Владелец разрешил **любое обучение, если оно перспективно поможет решить главную боль**: содержательный, достоверный визуальный сюжет, подробные музыкальные слои/переходы и устойчивый CPU-only offline realtime. Это включает adapter/projector, LoRA, encoder/LLM fine-tuning, distillation и альтернативные модели. **Повторного согласования каждого эксперимента не требуется.**

**До GPU training:** (1) подтверждённый interface/conditioning и правдоподобный CPU deploy path; (2) права на данные и source-separated train/val/held-out; (3) зафиксированный baseline и независимые quality metrics; (4) bounded GPU budget, checkpoints и stop conditions; (5) письменный `F10-GO.md` с результатом `GO`. Если что-то не выполнено — `NO-GO`, не скрывать риск. После короткого пилота продолжать лишь при измеренном улучшении без роста ложных утверждений. В production новые веса попадут только после held-out A/B и sustained 1x CPU live. Это разрешение на исследование, **не доказательство, что обучение обязательно поможет**.


## Точный рецепт для coding-агента

Выполнять [F10-multimodal-training-design.md](F10-multimodal-training-design.md): IMAGE — одно изображение и отношения объектов, VIDEO — временная последовательность кадров/сюжет, AUDIO — инструменты/музыкальные слои, AV — общая синхронизированная история. Там определены формы входов и выходов, source-separated JSONL, два адаптера vision/audio, маски отсутствующих модальностей, loss на целевых токенах JSON и русского описания, стартовый optimizer и критерии CPU realtime. Это гипотеза разработки до измерений, не готовая обученная модель.
