# F10 — исполняемое задание coding-агенту

> 26.10.2026. **Не запускать новый Deep Research.** Последний сеанс остановлен без отчёта. Ниже — проверенные проблемы SHSD и отдельно инженерные гипотезы. Владелец **разрешил любое перспективное обучение** при documented technical/data/CPU/budget GO; повторно спрашивать разрешение не нужно.

См. [Workspace](../../Workspace.md), [Todo](../../Todo.md), [ADR-002](../adr/ADR-002-multimodal-bridge-evaluation.md), [event graph](../architecture/grounded-av-storytelling.md), [pilot](bridge-training-pilot.md), [GO template](F10-GO.template.md).

## Главная боль и ограничения

Нужен **достоверный русский визуальный сюжет**, а не набор frame tags: устойчивые персонажи/объекты, действия, взаимодействия и их порядок. **Равноправно** нужна детальная музыка: слои, инструменты/семейства, вокал/бас/ударные, overlap с речью и появление/исчезновение/смена во времени. CPU-only offline production, устойчивый 1x live; GPU допускается для обучения. EmbeddingGemma 2 + Qwen3-0.6B остаются baseline до A/B и отдельного production decision.

**Latest 90s B0 graph baseline:** 62 L1 and 62 L2 revisions, 3 Russian L3 descriptions, 0 new accepted L2 details, 0 accepted semantic transitions, and 2 safe fallbacks; the 27.91s run was warm-cache offline analysis, not realtime or labeled quality. An earlier run did produce one unverified percussion detail; do not mix those run counts. **60s 1x live reference:** capture 41.828/60, 503 shared-prefetch drops, L1 lag p50 22.27s. L2 claims may not be expressed by Qwen even when input IDs are marked used. None of these results proves training will help.

**F10.01 result (2026-10-26):** local smoke tests verified EmbeddingGemma pre-pooling tokens for IMAGE/VIDEO/AUDIO/AV, a real Q8_0 Qwen3 GGUF external prefix through llama.cpp b11886, and production-provider sequence features/masks/token IDs/source PTS on CPU. See [`capability_matrix.md`](../../benchmarks/reports/bridge_f10/capability_matrix.md), [`production_sequence_smoke.json`](../../benchmarks/reports/bridge_f10/production_sequence_smoke.json) and raw JSON. A typed `AVFeatureBatch` now groups each IMAGE sequence with its exact PTS and keeps AUDIO as a separate interval; the dataset schema/validator records rights, annotation completeness, and split leakage. These are interfaces, not a trained or integrated bridge: prefix values are untrained, default analyze still pools, the adapter is not connected to B0, and sustained 1× CPU performance is unverified. Current training decision and exact missing gates: [`F10-GO.md`](../../benchmarks/reports/bridge_f10/F10-GO.md).
**B0 implementation result:** `analyze` emits typed temporal claim-graph records and builds Qwen inputs from accepted grounded claims in offline and live L3 paths. The current graph has event revisions and start-order links only; it does not infer visual entities/actions or music-layer events, and it does not consume the unpooled feature adapter yet.

## Контролируемые варианты

| Вариант | Назначение |
|---|---|
| A0 | Текущий frozen SHSD baseline |
| B0 | Grounded typed temporal event graph → **текстовый** Qwen, без обучения |
| B1 | Frozen EmbeddingGemma + frozen Qwen + **обучаемый** small projector/resampler |
| B2 | B1 + LoRA/partial fine-tune, только если B1 перспективен |
| C | Специализированные frozen audio/music и visual action/tracking encoders + graph |
| D | Готовая compact AV/VLM/audio-language модель, только после лицензий и CPU benchmark |

Pooled embedding — контроль, не гарантия, что сохраняются инструменты, действия и время. Если фактов нет в features, не учить Qwen угадывать.

## Четыре последовательных коммита

### A. Исполняемая проверка интерфейсов — без обучения
- Pin model revisions и preprocessing. На 5s audio + sampled frames проверить encoder outputs: pooled, а если API поддерживает — patch/time tokens, shapes, masks, timestamps, CPU encoder latency.
- Qwen3-0.6B: synthetic non-text `inputs_embeds` forward/generate and prefix gradient path without training; also test the actual GGUF native C API path. Do not call a text prompt a multimodal prefix.
- CPU GGUF/llama.cpp: external-prefix API is verified; measure prefill/decode and RSS again under the later stream workload. API smoke alone is not a realtime result.
- Сохранить exact commands, exit codes, upstream references, licenses, verified/unsupported/unknown в benchmarks/reports/bridge_f10/capability_matrix.md.
- **NO-GO для B1**, если conditioning или CPU deploy path отсутствует; продолжить B0/C.

### B. Grounded graph, B0 и независимая оценка — без обучения
- Typed entity/action/music_layer/AV relation, source PTS/epoch/evidence/uncertainty/revisions; сохранить совместимость SQLite/JSONL/API.
- B0: graph→grounded facts→Qwen3-0.6B; проверить input/expressed/omitted claims, unsupported additions и temporal order.
- Независимые human-labeled evaluation intervals: 10–20 для пилота, затем расширять; speech-only, music-only, overlap, music layer changes, visual actions, hard negatives. Eval **не** training. Source-separated, права/аннотаторы/unknown.
- A0/B0 same-source A/B с per-interval raw errors; создать benchmarks/reports/bridge_f10/F10-GO.md из [шаблона](F10-GO.template.md) с законными **отдельными** train/val/held-out и bounded GPU budget.
- **GO B1** только при проверенных API, CPU path, правах, независимом baseline, заранее зафиксированных success/stop criteria.

### C. Короткий B1 training pilot — после GO
- Frozen EmbeddingGemma и Qwen; учить только projector/resampler. Начать с train-only sanity overfit, затем bounded pilot. Записать seeds, hyperparameters, checkpoint, GPU-hours/VRAM, data manifest и validation curves.
- B0 vs B1 на одинаковых источниках/evidence. Ablations: audio-only, video-only, swapped audio, shuffled time, missing modality.
- Human-verified held-out: visual action/identity/order, music layers/transitions, unsupported claims/omissions, RU coherence. Измерить CPU 1x pre-stop C/E/R lag slope, drops, RSS, prefill/decode.
- **Продолжать** только при заранее заданном измеримом улучшении хотя бы одной primary оси, без деградации другой/роста ложных фактов, и с реалистичным CPU path. Если нет — STOP, не подгонять held-out.

### D. Альтернативы и решение
- B1 помогает, но frozen Qwen плохо принимает информацию: bounded B2 LoRA/другое обучение по следующему budget GO.
- B1 не помогает из-за бедных features: C — frozen специализированные music/audio и video action/tracking perception, не бесконечный fine-tune.
- GPU demo без CPU custom prefix: B0/C, не production bridge.
- Финал: A0/B0/B1/B2/C на независимом качестве и sustained 1x unique-media cold-cache. Решение ship frozen / ship bridge / specialized perception / NO-GO, отдельная ADR для production.

## Не засчитывать успехом

Снижение train loss без новых grounded facts; красивые выдуманные действия/инструменты; music runner-up→percussion без premise; input claim ошибочно отмечен expressed; 55s/90s file-mode вместо live; post-stop drain вместо pre-stop; test source в training/tuning; PyTorch GPU-only prefix вместо CPU deployment.

**Отчёт каждого коммита:** SHA, exact commands/exit codes, model revisions, tests, source IDs/splits/licenses, manual-label N, TP/FP/FN, unsupported/omitted claims, visual temporal order/music transitions, CPU pre-stop lag/drops/RSS, raw artifacts и GO/NO-GO.


## Обязательная конкретизация обучаемого B1: IMAGE, VIDEO, AUDIO, AV

**Новый первичный технический документ: [F10-multimodal-training-design.md](F10-multimodal-training-design.md).** В нём даны input tensor shapes, missing-modality masks, четыре JSONL sample modes, target visual_entities/visual_actions/music_layers/av_relations + `caption_ru`, supervised target-only next-token CE, initial AdamW/grid/step limits, тесты и GO.

Coding-агент обязан реализовать **как минимум две самостоятельные визуальные проверки**: IMAGE-only объектно-пространственное описание одиночного изображения без выдуманного движения; VIDEO-only упорядоченный сюжет с устойчивыми entity IDs, subject/action/object и до/после. AUDIO/music и синхронный AV — отдельные режимы и metrics. Один music_presence/instrument classifier не равен итоговой цели.

**Next:** continue F7.03 independent labels and F9.01 live backlog; extend the integrated B0 claim graph with independently supported visual entity/action and music-layer nodes; connect the sequence API with validated PTS alignment; build an independent evaluator and same-source A0/B0 comparison. F10.03 projector training remains behind documented technical/data/budget GO.
