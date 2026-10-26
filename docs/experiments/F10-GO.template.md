# F10-GO — шаблон gate перед обучением

> **NOT EVALUATED.** Владелец разрешил перспективное обучение 26.10.2026; этот файл не означает, что технический GO уже пройден. Копировать в benchmarks/reports/bridge_f10/F10-GO.md и заполнить фактами.

## Гипотеза
- Вариант B1/B2/C: TBD
- Какую боль решает (visual actions, music transitions, AV grounding, RU L3): TBD
- Почему B0 structured evidence недостаточен: TBD
- Ожидаемый измеримый эффект: TBD

## Technical gate
| Проверка | Статус | Доказательство |
|---|---|---|
| Encoder features / shapes / time tokens | unknown | model revision + exact smoke test |
| Qwen non-text conditioning / gradient path | unknown | exact smoke test |
| Offline CPU runtime / GGUF or alternative | unknown | measured CPU test |
| CPU prefill/decode/RSS feasibility | unknown | measurements |
| Model license / data rights | unknown | links |
| No cloud/GPU runtime dependency | unknown | dependency audit |

## Данные и quality
- Законные train sources, validation sources, source-separated held-out: TBD
- Independent manual labels: N, annotators, blind review, unknown: TBD
- Leakage prevention: TBD
- Baseline A0/B0 SHA, configs, model revisions: TBD
- Pre-registered visual action/order and music layer/transition minimum delta: TBD
- Unsupported claims, non-degradation of other axis: TBD
- 1x CPU pre-stop C/E/R lag slope, drops, RSS thresholds: TBD
- Audio-only/video-only/swapped-audio/shuffled-time ablations: TBD

## Ресурсы и остановка
- GPU, max GPU-hours, VRAM, disk, checkpoints: TBD
- Seed, steps, optimizer, validation cadence: TBD
- Early STOP on no gain, hallucinations, CPU failure, rights issue, budget: TBD
- Next-stage B2 budget gate: TBD

**Decision: NOT EVALUATED (GO / NO-GO / BLOCKED)**. Evidence reviewer/date/SHA: TBD. Unknown не считается GO. Никаких production changes до independent held-out A/B и sustained CPU 1x.


## Обязательный визуальный gate

До GO отдельно проверить: IMAGE-only object/relation quality без вымышленных движений; VIDEO-only subject-action-object, entity continuity, shuffled frames и таймкоды; AUDIO-only instrument/layer/transition; AV shifted audio/false causality. Проверить missing modality masks, target-only CE и source-separated train/test для всех режимов. Недостаточное качество IMAGE или VIDEO нельзя компенсировать музыкой. Полный [training design](F10-multimodal-training-design.md).
