# F10 — исполняемый дизайн мультимодального обучения SHSD: IMAGE, VIDEO, AUDIO, AV

> Версия 1, 26.10.2026. **Инженерная спецификация, не отчёт завершённого Deep Research и не измеренный результат.** Владелец разрешил любое перспективное обучение при подтверждённой технической возможности, законных данных и ограниченном бюджете. Production — offline CPU realtime. **Визуальный сюжет и изображения равноправны музыке.** Если улучшаются только музыкальные теги, а IMAGE/VIDEO остаются набором тегов, проект НЕ принят.

[Задачи](../../Todo.md) · [F10 handoff](F10-agent-handoff.md) · [EventGraph](../architecture/grounded-av-storytelling.md) · [GO template](F10-GO.template.md) · [ADR-002](../adr/ADR-002-multimodal-bridge-evaluation.md).

## 1. Обязательные четыре режима (обучение и независимая оценка)

| Mode | Вход | Grounded русский выход | Negative controls |
|---|---|---|---|
| IMAGE | Одно статическое изображение, аудио нет | Виден человек/объект, атрибуты и пространственные отношения | Нельзя выдумывать предшествующие действия, музыку или диалог |
| VIDEO | **Упорядоченные** кадры с исходными PTS; аудио нет | Сущности сохраняются во времени; субъект совершает действие над объектом; порядок «сначала/потом», сцены и изменения | Shuffle/reverse frames, cross-shot entity identity, не подменять сюжет frame tags |
| AUDIO | Аудио без изображения | Speech/music/ambience overlap, подтверждённые percussion/bass/vocals и инструментальные семьи, появление/исчезновение слоёв | Speech-only, ambience-only, нет вымышленных видимых объектов |
| AV | Аудио+кадры и source PTS | Единый русский сюжет с действиями и развитием музыки; только подтверждённые AV связи | Swapped/shifted audio, coincidence ≠ causality |

**Gates независимы:** IMAGE object/relation precision, VIDEO entity/action/order, AUDIO instruments/layers/transitions, AV sync/false causal claims, русский factual L3 и CPU 1x lag/drops. Хорошая AUDIO метрика не закрывает провал изображения/видео.

## 2. Архитектура, которую агент реализует

A0 — текущий frozen EmbeddingGemma 2 → semantic/temporal events → Qwen3-0.6B. B0 — новый typed EventGraph (objects, visual relations, tracked actions, music layers) → компактный текстовый evidence → frozen Qwen, **без обучения**. B0 нужен, чтобы отличать улучшение perception от улучшения самого multimodal bridge.

**B1 — первая trainable baseline:**
1. Frozen EmbeddingGemma 2 возвращает отдельно image/frame и audio признаки; **реальную поддержку pooled и sequence/patch/time outputs установить F10.01**, а не предполагать.
2. Vision branch: image/frame tokens + source PTS/time embeddings → лёгкий trainable projector/resampler → visual prefix. IMAGE=один frame без fake motion; VIDEO=временная последовательность.
3. Audio branch: audio features + time embeddings → отдельный trainable projector/resampler → audio prefix. Music layers/ASR evidence хранятся отдельно.
4. Temporal fusion объединяет source-time последовательность, учитывает modality masks и ограничивает число prefix tokens. Не вводить тяжёлый temporal transformer до необходимости.
5. Prefix embeddings размерности `D_q` (прочитать из фактического Qwen3-0.6B checkpoint) + prompt/target token embeddings подаются в frozen Qwen через **реально проверенный** conditioning interface (`inputs_embeds`/эквивалент).
6. Qwen выдаёт **структурированные grounded events + связное `caption_ru`**. Claim verifier отдельно проверяет evidence и input/expressed/omitted claim IDs. Сгенерированный текст сам по себе не доказательство факта.
7. Обучаются **только** vision projector, audio projector, resampler/temporal embeddings; EmbeddingGemma 2 и Qwen заморожены. B2 LoRA/encoder tuning — при измеренной перспективе B1 и отдельном bounded budget. C — специализированное perception/action tracking/music модели, если pooled encoder теряет нужную информацию.

**Не принимать:** случайное 768d→Qwen отображение как рабочий bridge, PyTorch GPU training вместо подтверждённого CPU deployment, обещания GGUF custom-prefix support без исполнения.

## 3. Typed FeatureBatch / masks

`vision_features: float[B,Tv,Nv,Dv]` token/patch или `float[B,Tv,Dv]` pooled frames; `vision_pts_ms: int64[B,Tv]`; `vision_valid`. IMAGE=Tv=1; VIDEO=Tv>1, PTS строго упорядочен в каждом epoch.

`audio_features: float[B,Ta,Na,Da]` token/time или `float[B,Ta,Da]` pooled; `audio_start_ms, audio_end_ms: int64[B,Ta]`; `audio_valid`; preprocessing из модели.

`modality_present: bool[B,2]` vision/audio; `mode` IMAGE|VIDEO|AUDIO|AV; `source_id,epoch,start_ms,end_ms`.

Output: `prefix_v: float[B,Kv,Dq]`, `prefix_a: float[B,Ka,Dq]`, optional `prefix_t: float[B,Kt,Dq]`; `prefix_attention_mask`, frame/source timestamps, provenance. **Отсутствующая модальность имеет 0 валидных slots или полностью masked slots**, а не фиктивное изображение/музыку. Размеры `Dv,Da,Dq` из загруженных конфигов/shape tests, не «магические».

**Стартовые HYPOTHESIS defaults, не измерения:** 5s online windows; IMAGE 1 frame; VIDEO до 4 разных frames/5s (start/mid/end/cut) с реальными PTS; временная память 2–4 соседних окна (10–20s) только если CPU бюджет позволяет, **никаких будущих кадров в live eval**. Prefix budget `Kv=8,Ka=8,Kt=0–4`; sweep `(4,4),(8,8),(16,8)`. Кэш feature версионировать по model SHA/preprocess/source.

## 4. JSONL training sample и выход

**Split по исходным фильмам/источникам/сериям, не по окнам или извлечённым кадрам.** Лицензия и право на обучение, local files, SHA, human verification, annotator. Независимый held-out не использовать в train, tuning и для pseudo-label prompts.

`sample_id,source_id,split,mode,epoch,start_ms,end_ms`; `frames:[{path,pts_ms}]` и `audio:[{path,start_ms,end_ms}]`; `modality_present:{vision,audio}`; `target`; `verified,license_id,annotator`.

`target`:
- `visual_entities:[{entity_id,label_ru,attributes?,evidence_frame_ms}]`;
- `visual_relations:[{subject_id,relation,object_id,evidence_frame_ms}]`;
- `visual_actions:[{subject_id,verb_ru,object_id?,start_ms,end_ms,evidence_frame_ms}]`;
- `music_layers:[{layer_id,instrument_family_ru?,instrument_ru?,onset_ms?,offset_ms?,transition?,evidence_audio_ms}]`;
- `av_relations:[{visual_event_id,audio_event_id,relation,evidence_refs}]`;
- `caption_ru` — связный русский текст с хронологией, без выдуманных мотивов/инструментов.

Пример СХЕМЫ IMAGE-only (не реальное наблюдение):

```json
{"sample_id":"illustration-001","source_id":"licensed-img-1","split":"train","mode":"IMAGE",
 "epoch":0,"start_ms":0,"end_ms":1,
 "frames":[{"path":"images/001.jpg","pts_ms":0}],"audio":[],
 "modality_present":{"vision":true,"audio":false},
 "target":{"visual_entities":[{"entity_id":"p1","label_ru":"человек","evidence_frame_ms":[0]}],
 "visual_relations":[],"visual_actions":[],"music_layers":[],"av_relations":[],
 "caption_ru":"На изображении виден человек."},
 "verified":true,"license_id":"rights-1","annotator":"human-verified"}
```

Для VIDEO action evidence должно ссылаться **на несколько PTS**. Для IMAGE не давать target «вышел», «прошёл», «открыл» без наблюдения последовательности. Music presence и instrument specificity проверять отдельно; acoustic novelty ≠ instrument change. Teacher-generated text без проверки не является истинным supervised factual target.

## 5. Loss, output masking и optimizer — фиксированный начальный recipe

**B1 loss — supervised conditional next-token cross-entropy** на русском `target JSON + caption_ru`.

- Teacher forcing: `inputs_embeds = concat(prefix_embeddings, prompt_token_embeddings, target_token_embeddings)` с causal shifting, соответствующим **реальному Qwen API**. Prompt содержит задачу/режим, **не** готовые метки и подписи.
- `labels=-100` для prefix, prompt, padding и отсутствующих modality slots. **Только target tokens** имеют supervision. Tokenization/shift/position IDs проверить ручным unit-тестом.
- `L_mode = sum_valid_target_tokens(-log P(y_t|prefix,prompt,y_<t)) / N_valid`. Общий objective — **макро-среднее по IMAGE/VIDEO/AUDIO/AV**, либо modality-balanced sampler с отчётом о раздельных mode losses. Не маскировать отсутствие visual примеров множеством audio.
- `verified=false` и unsupported pseudo-facts не учить как истину. Начать без auxiliary loss; при обнаруженном bottleneck временного порядка/слоёв добавить отдельно **размеченный** temporal/order/transition loss в B2 и провести ablation.
- Gradient flow через frozen Qwen к projector; **весовые тензоры EmbeddingGemma и Qwen не меняются**. После шага проверить grad/non-grad и equality параметров.

**Стартовая гипотеза обучения, НЕ измеренный optimum:** AdamW только projectors/resampler, `lr=1e-4` (val sweep 3e-5/1e-4/3e-4), `weight_decay=0.01`, `gradient_clip=1.0`, `warmup_ratio=0.03`, cosine decay, `seed=42`, per-device microbatch 1, accumulation до approx effective batch 16 по VRAM, BF16 только при подтверждённой поддержке. Первый pilot **≤1000 optimizer steps или ≤3 epochs, что наступит раньше**, плюс explicit max GPU-hours. IMAGE/VIDEO/AUDIO/AV balanced sampling ~25% каждый **при наличии законных данных**.

Перед training: (1) синтетический shape/collator smoke без training; (2) single forward/backward finite CE и frozen params; (3) few-sample **train-only** overfit sanity для всех четырёх режимов; (4) independent val/held-out, raw per-sample errors, CPU runtime tests. Ни train loss, ни output JSON validity не доказательство grounded story.

## 6. Рекомендуемые файлы/коммиты

| Предлагаемый новый путь | Ответственность |
|---|---|
| `src/shsd/bridge/features.py` | Typed FeatureBatch, PTS, mode masks |
| `src/shsd/bridge/dataset.py` | JSONL rights/split validation, IMAGE/VIDEO/AUDIO/AV |
| `src/shsd/bridge/projector.py` | Vision/audio projections, temporal resampler and prefix |
| `src/shsd/bridge/collator.py` | Qwen input/target tokenization, labels=-100, masks/shift |
| `src/shsd/bridge/train.py` | Frozen models, bridge-only optimizer, checkpoints |
| `src/shsd/bridge/infer.py` | CPU-only conditioning smoke, timings/prefix |
| `src/shsd/bridge/eval.py` | Per-mode independent metrics and L3 factuality |
| `tests/unit/test_bridge_*.py` | shapes, modes, frozen weights, train mask, temporal negative tests |
| `benchmarks/reports/bridge_f10/` | capabilities, F10-GO, manifests, errors, CPU live |

**PR1:** actual encoder/Qwen/CPU shape APIs. **PR2:** typed dataset, B0 grounded EventGraph and eval. **PR3:** B1 bridge train after GO. **PR4:** blind held-out per-mode ablations and sustained CPU 1x.

## 7. Tests, GO / NO-GO

- IMAGE-only: 1 frame, audio mask false, no hallucinated motion/music.
- VIDEO-only: ordered timestamps, tracked entity/action evidence, shuffled/reverse order negative test.
- AUDIO-only: vision false, voice/music overlap, instruments/layers/changes, no phantom visible people.
- AV: shifted/swapped audio, no fabricated source attribution/causality.
- Mixed batch: correct shapes/attention masks/labels, finite losses, no target leakage; bridge-only grads, frozen model weights unchanged.
- No GPU requirement for production; Qwen CPU multimodal-prefix path **must be verified** (GGUF or alternate). If unsupported, `NO-GO` for B1 deployment, not fake text fallback.
- 1x live cold unique media: pre-stop C/E/R, lag p50/p95/slope, drops, RSS/prefill/token/s; repeated file warm cache ≠ realtime.
- Independent human-labeled IMAGE objects/relations, VIDEO actions/identity/order, AUDIO instrument/music transitions, AV sync, unsupported claims/omissions, Russian coherent narration.

**GO training:** all [F10-GO](F10-GO.template.md) fields backed by source/command; licenses, independent splits, feature+Qwen API, plausible CPU path, bounded GPU budget, **registered per-mode thresholds**. Владелец разрешил перспективное обучение; не требуется новое исследование. **GO production:** B1 improves grounded factuality of visual storytelling and music (no unacceptable regression in either) and meets CPU 1x. **NO-GO:** text unaffected by shuffled frames/swapped audio, fabricated details, image/video failures, no CPU path, dataset rights missing, growing live backlog.
