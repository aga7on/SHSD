# F10 — Multimodal AV Bridge: исполняемый дизайн обучения SHSD для IMAGE, VIDEO, AUDIO и AV

> Версия 2, 26.10.2026. **Инженерная спецификация, не отчёт завершённого Deep Research и не измеренный результат.** Владелец разрешил любое перспективное обучение при подтверждённой технической возможности, законных данных и ограниченном бюджете. Production — offline CPU realtime. **Визуальный сюжет и изображения равноправны музыке.** Если улучшаются только музыкальные теги, а IMAGE/VIDEO остаются набором тегов, проект НЕ принят.

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
1. Frozen EmbeddingGemma 2 returns a pooled 768-vector and pre-pooling `token_embeddings` for IMAGE/VIDEO/AUDIO/AV (verified in F10.01). `EmbeddingProvider` exposes opt-in `SequenceFeatureRecord` methods with token masks/IDs and source PTS; see [`production_sequence_smoke.json`](../../benchmarks/reports/bridge_f10/production_sequence_smoke.json). [`AVFeatureBatch`](../../src/shsd/bridge/features.py) creates an alignment-safe representation by keeping one IMAGE token sequence per sampled source PTS plus a separate interval AUDIO sequence. It does not guess which flattened VIDEO token belongs to a frame. This adapter is not yet connected to EventGraph or default `analyze`.
2. Vision branch: image/frame tokens + source PTS/time embeddings → лёгкий trainable projector/resampler → visual prefix. IMAGE=один frame без fake motion; VIDEO=временная последовательность.
3. Audio branch: audio features + time embeddings → отдельный trainable projector/resampler → audio prefix. Music layers/ASR evidence хранятся отдельно.
4. Temporal fusion объединяет source-time последовательность, учитывает modality masks и ограничивает число prefix tokens. Не вводить тяжёлый temporal transformer до необходимости.
5. Prefix embeddings of width `D_q=1024` (read from the actual Qwen3-0.6B GGUF) + prompt/target tokens are passed into frozen Qwen. The pinned llama.cpp CPU external-embedding C API path passed F10.01 smoke; learned prefix quality remains unknown.
6. Qwen выдаёт **структурированные grounded events + связное `caption_ru`**. Claim verifier отдельно проверяет evidence и input/expressed/omitted claim IDs. Сгенерированный текст сам по себе не доказательство факта.
7. Обучаются **только** vision projector, audio projector, resampler/temporal embeddings; EmbeddingGemma 2 и Qwen заморожены. B2 LoRA/encoder tuning — при измеренной перспективе B1 и отдельном bounded budget. C — специализированное perception/action tracking/music модели, если pooled encoder теряет нужную информацию.

**Не принимать:** случайное 768d→Qwen отображение как рабочий bridge, PyTorch GPU training вместо подтверждённого CPU deployment, или выводы о качестве/1x realtime из API smoke. Native GGUF prefix transport has been executed; it still needs learned-quality and sustained-stream evaluation.

## 3. Typed FeatureBatch / masks

`vision_features: float[B,Tv,Nv,Dv]` token/patch или `float[B,Tv,Dv]` pooled frames; `vision_pts_ms: int64[B,Tv]`; `vision_valid`. IMAGE=Tv=1; VIDEO=Tv>1, PTS строго упорядочен в каждом epoch.

`audio_features: float[B,Ta,Na,Da]` token/time или `float[B,Ta,Da]` pooled; `audio_start_ms, audio_end_ms: int64[B,Ta]`; `audio_valid`; preprocessing из модели.

`modality_present: bool[B,2]` vision/audio; `mode` IMAGE|VIDEO|AUDIO|AV; `source_id,epoch,start_ms,end_ms`.

Output: `prefix_v: float[B,Kv,Dq]`, `prefix_a: float[B,Ka,Dq]`, optional `prefix_t: float[B,Kt,Dq]`; `prefix_attention_mask`, frame/source timestamps, provenance. **Отсутствующая модальность имеет 0 валидных slots или полностью masked slots**, а не фиктивное изображение/музыку. Размеры `Dv,Da,Dq` из загруженных конфигов/shape tests, не «магические».

**Стартовые HYPOTHESIS defaults, не измерения:** окно 5s, stride 2.5s; IMAGE — один frame; VIDEO — sparse 1–2 fps либо до четырёх keyframes/5s (start/mid/end/cut) с реальными PTS; AUDIO — весь 5s chunk; память 2–4 соседних окна (10–20s) только если CPU бюджет позволяет, никаких будущих кадров в live eval. Prefix budget Kv=8, Ka=8, Kt=0–4; sweep (4,4), (8,8), (16,8). Это стартовая сетка, не измерения. Кэш feature версионировать по model SHA/preprocess/source.

**Правило masks и perturbations:** IMAGE/VIDEO/AUDIO/AV задаются истинной modality_present маской; отсутствующие slots имеют нулевую attention mask. Пример с dropped modality допускается в training только если target очищен от claims, требующих отсутствующего канала. Swapped/shifted audio и shuffled/reversed frames — прежде всего held-out ablations/negative controls; не обучать на испорченном сочетании с исходным правильным target.

## 4. JSONL training sample и выход

Исполняемая JSON Schema v1: [`configs/schemas/av_bridge_sample_v1.schema.json`](../../configs/schemas/av_bridge_sample_v1.schema.json). Межполевые правила (PTS, ссылки на сущности/события, маски, лицензии, утечки split) проверяются [`scripts/validate_bridge_dataset.py`](../../scripts/validate_bridge_dataset.py):

```powershell
python scripts/validate_bridge_dataset.py data/manifest.jsonl --media-root data/media
```

Один JSONL record — одно окно, а split назначается всей исходной группировке `source_group_id` (фильм, эпизод или источник), не отдельным кадрам/окнам. `source_sha256` фиксирует оригинал; пути в `frames` и `audio` относительны к media root; frame PTS и audio intervals даны в миллисекундах исходного источника. Для каждого split права должны явно разрешать `train`, `validation` или `evaluation`. Training/evaluation samples требуют `human_verified`, ID аннотатора и версию руководства. Данные не включать в репозиторий без отдельной необходимости и прав.

`target` требует все группы: `visual_entities`, `visual_relations`, `visual_actions`, `scene_events`, `audio_scene`, `speech_segments`, `music_layers`, `av_relations`, `temporal_relations` и `caption_ru`. События и сущности имеют устойчивые внутри исходника IDs и frame/audio evidence. В `audio_scene` значения `present|absent|unknown`; coverage отдельно маркируется как `complete|partial|not_applicable`. Отсутствующая или частичная разметка не превращает ненаблюдаемое в negative label и не получает coverage loss. Примеры без аудио обязаны иметь unknown audio labels; без видео — пустые visual targets. AV relation хранит отдельные ссылки на визуальное и аудио evidence, но совпадение по времени само по себе не кодирует причинность.

Короткий IMAGE-only пример (синтетический пример схемы, не размеченный training data):

```json
{
  "schema_version": 1,
  "sample_id": "illustration-001",
  "source_id": "licensed-img-1",
  "source_group_id": "licensed-img-1",
  "source_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "split": "train",
  "mode": "IMAGE",
  "epoch": 0,
  "start_ms": 0,
  "end_ms": 1,
  "frames": [{"path": "images/001.jpg", "pts_ms": 0}],
  "audio": [],
  "modality_present": {"vision": true, "audio": false},
  "target": {
    "visual_entities": [{"entity_id": "p1", "label_ru": "человек", "evidence_frame_ms": [0]}],
    "visual_relations": [], "visual_actions": [], "scene_events": [],
    "audio_scene": {"speech": "unknown", "music": "unknown", "ambience": "unknown", "overlap": "unknown"},
    "speech_segments": [], "music_layers": [], "av_relations": [], "temporal_relations": [],
    "coverage": {
      "visual_entities": "complete", "visual_relations": "complete",
      "visual_actions": "not_applicable", "scene_events": "not_applicable",
      "audio_scene": "not_applicable", "speech_segments": "not_applicable",
      "music_layers": "not_applicable", "av_relations": "not_applicable",
      "temporal_relations": "not_applicable"
    },
    "caption_ru": "На изображении виден человек."
  },
  "rights": {"license_id": "rights-1", "permitted_uses": ["train"]},
  "annotation": {"verification": "human_verified", "annotator_id": "reviewer-1", "guide_version": "f10-v1"}
}
```

IMAGE не допускает actions/scene flow; для VIDEO action evidence должно ссылаться минимум на два исходных sampled PTS. Для AUDIO/AV music onset, offset и слой подтверждаются отдельным аудио evidence. Acoustic novelty ≠ instrument change. Teacher-generated text без независимой human-проверки не является supervised factual target. Для B1 coverage/absence targets используют только полно размеченные группы; `unknown` и `partial` исключаются из negative supervision.

## 5. Loss, output masking и optimizer — начальный recipe

Базовая цель B1 — supervised conditional next-token CE на обоих типах target: структурированных AV claims/relations и caption_ru. Явно считать:

L_total = lambda_caption * L_caption
        + lambda_struct  * L_struct
        + lambda_align   * L_align
        + lambda_cov     * L_coverage

- L_caption: autoregressive token loss по русскому caption при teacher forcing.
- L_struct: token loss по target JSON; если structured claims вынесены в отдельные multi-label heads, применять BCE/CE к entity/action, audio_scene/music-layer и transition labels. Не учитывать один target дважды: разделять spans или считать единый CE по общей структуре и caption.
- L_align: опциональная contrastive/ranking или relation-prediction потеря для before/after/overlap, только при достаточных human-verified time/AV relation labels.
- L_coverage: опциональная omission/coverage потеря по полностью размеченным положительным claims; unknown или неполная разметка не является отрицанием. Не повышать recall ценой неподтверждённых фактов.
- Первый B1 pilot начинает с L_caption + L_struct на serialized targets; lambda_align=lambda_cov=0 до появления размеченного bottleneck и отдельного ablation. Весовые коэффициенты и критерии выбрать на train/validation и preregister до held-out, никогда не настраивать по test.

Teacher forcing: inputs_embeds = concat(prefix_embeddings, prompt_token_embeddings, target_token_embeddings) с causal shifting, соответствующим реальному Qwen API. Prompt содержит задачу/режим, не готовые метки и подписи.
- labels=-100 для prefix, prompt, padding и отсутствующих modality slots. Только target tokens имеют supervision. Tokenization/shift/position IDs проверить тестом.
- L_mode = sum_valid_target_tokens(-log P(y_t|prefix,prompt,y_<t)) / N_valid. Общий objective — макро-среднее по IMAGE/VIDEO/AUDIO/AV, либо modality-balanced sampler с отчётом о раздельных mode losses. Не маскировать отсутствие visual примеров множеством audio.
- verified=false и unsupported pseudo-facts не учить как истину.
- Gradient flow идёт через frozen Qwen к projector; весовые тензоры EmbeddingGemma и Qwen не меняются. После шага проверить grad/non-grad и equality параметров.

Начальная гипотеза обучения, не измеренный optimum: AdamW только projectors/resampler, lr=1e-4 (validation sweep 3e-5/1e-4/3e-4), weight_decay=0.01, gradient_clip=1.0, warmup_ratio=0.03, cosine decay, seed=42, per-device microbatch 1, accumulation до approx effective batch 16 по VRAM, BF16 только при подтверждённой поддержке. Первый pilot ≤1000 optimizer steps или ≤3 epochs (что наступит раньше), плюс explicit max GPU-hours. IMAGE/VIDEO/AUDIO/AV balanced sampling ~25% каждого при наличии законных данных.

Перед training: (1) синтетический shape/collator smoke без training; (2) single forward/backward finite CE и frozen params; (3) few-sample train-only overfit sanity для всех четырёх режимов; (4) independent val/held-out, raw per-sample errors, CPU runtime tests. Ни train loss, ни output JSON validity не доказательство grounded story.

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
- No GPU requirement for production; the pinned Qwen GGUF CPU multimodal-prefix transport is verified by F10.01. Learned-quality and sustained 1× stream tests remain mandatory; if either fails, no B1 deployment.
- 1x live cold unique media: pre-stop C/E/R, lag p50/p95/slope, drops, RSS/prefill/token/s; repeated file warm cache ≠ realtime.
- Independent human-labeled IMAGE objects/relations, VIDEO actions/identity/order, AUDIO instrument/music transitions, AV sync, unsupported claims/omissions, Russian coherent narration.

**GO training:** all [F10-GO](F10-GO.template.md) fields backed by source/command; licenses, independent splits, feature+Qwen API, plausible CPU path, bounded GPU budget, **registered per-mode thresholds**. Владелец разрешил перспективное обучение; не требуется новое исследование. **GO production:** B1 improves grounded factuality of visual storytelling and music (no unacceptable regression in either) and meets CPU 1x. **NO-GO:** text unaffected by shuffled frames/swapped audio, fabricated details, image/video failures, no CPU path, dataset rights missing, growing live backlog.
