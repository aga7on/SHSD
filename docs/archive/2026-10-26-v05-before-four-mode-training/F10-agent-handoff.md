# F10 — исполняемое задание coding-агенту

> 26.10.2026. **Не запускать новый Deep Research.** Последний сеанс остановлен без отчёта. Ниже — проверенные проблемы SHSD и отдельно инженерные гипотезы. Владелец **разрешил любое перспективное обучение** при documented technical/data/CPU/budget GO; повторно спрашивать разрешение не нужно.

См. [Workspace](../../Workspace.md), [Todo](../../Todo.md), [ADR-002](../adr/ADR-002-multimodal-bridge-evaluation.md), [event graph](../architecture/grounded-av-storytelling.md), [pilot](bridge-training-pilot.md), [GO template](F10-GO.template.md).

## Главная боль и ограничения

Нужен **достоверный русский визуальный сюжет**, а не набор frame tags: устойчивые персонажи/объекты, действия, взаимодействия и их порядок. **Равноправно** нужна детальная музыка: слои, инструменты/семейства, вокал/бас/ударные, overlap с речью и появление/исчезновение/смена во времени. CPU-only offline production, устойчивый 1x live; GPU допускается для обучения. EmbeddingGemma 2 + Qwen3-0.6B остаются baseline до A/B и отдельного production decision.

**Baseline:** 90s file-mode: 3 общих L3, 1 accepted-but-not-human-verified percussion detail, 0 accepted semantic transitions; 60s 1x live: capture 41.828/60, 503 shared-prefetch drops, L1 lag p50 22.27s. L2 claims могут не быть выражены Qwen, хотя input IDs помечены used. Это **не** доказательство, что обучение поможет.

**Unknown до smoke tests:** EmbeddingGemma audio/video token/time features, Qwen inputs_embeds/custom prefix, CPU GGUF/llama.cpp deploy, точная стоимость и качество B1. Не утверждать непроверенное.

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
- Qwen3-0.6B: synthetic non-text conditioning smoke test, проверка inputs_embeds/prefix и gradient path **без training**. Не выдавать text prompt за мультимодальный prefix.
- Отдельно CPU GGUF/llama.cpp или иной offline CPU runtime: custom conditioning, prefill/decode, RSS.
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
