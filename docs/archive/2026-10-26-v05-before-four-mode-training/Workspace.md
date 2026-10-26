# Workspace.md — SHSD: текущая цель и архитектурная спецификация

> **Версия 0.5 · 26.10.2026 · статус: активный план улучшения качества и CPU realtime.**
> Исходная полная спецификация v0.1 сохранена [без изменений в архиве](docs/archive/2026-10-26-pre-multimodal-review/Workspace.md). Задачи — [Todo.md](Todo.md), правила — [Agents.md](Agents.md), протокол измерений — [docs/experiments/av-bridge-evaluation-protocol.md](docs/experiments/av-bridge-evaluation-protocol.md).
>
> **Практическое ТЗ:** [F10 coding-agent handoff](docs/experiments/F10-agent-handoff.md) · [AV event graph](docs/architecture/grounded-av-storytelling.md) · [F10-GO template](docs/experiments/F10-GO.template.md).
>
> **Граница:** целевой runtime остаётся offline/CPU-only. Существующая production-ветка пока training-free. **Обучаемый мультимодальный мост — отдельный параллельный R&D-трек F10 с конкретным протоколом**, а не отложенная заметка. **Владелец 26.10.2026 разрешил любое перспективное обучение** для улучшения grounded AV сюжета, музыки и temporal detail. Перед training — documented feasibility/data/budget `GO`, повторное разрешение не требуется.

## 1. Что строим

SHSD (Streaming Hierarchical Semantic Decoder) должен получать живые аудио и видео и **с небольшой измеренной задержкой** выдавать конкретные, проверяемые и связные **русскоязычные** описания происходящего. Важны одновременно:

1. **Музыка и её развитие:** различать музыку, речь и окружающую среду (включая их наложение); описывать реально различимые ударные, бас, вокал, семейства инструментов, тембр, энергию, ощущение темпа; замечать появление/исчезновение слоёв и переходы **во времени**, а не выдавать один общий ярлык.
2. **Визуальные события и сюжет:** кто/что видно, какие действия происходят и как меняются, устойчивость объектов между кадрами, порядок событий; не заменять содержание фразами «обнаружено изменение изображения».
3. **Своевременность:** обработка уникального 1x live источника без систематически растущего lag, потери покрытия и скрытого отбрасывания окон; 2x/5x — отдельные нагрузочные сценарии.

Всё, что модель не может подтвердить, помечать `uncertain/unknown/abstained`. Не превращать cosine similarity в вероятность и не выдумывать точные инструменты, BPM, действия, причинность или сюжетные мотивы.

## 2. Сохраняемые решения и контракты

- **EmbeddingGemma 2** (`google/embeddinggemma-2`) — реальный мультимодальный encoder аудио/кадров/текста; эмбеддинги и их модельные ревизии, не прямые токены Qwen.
- **Qwen3-0.6B** — локальный CPU narrator для русского L3, работающий с обоснованными структурированными событиями L1/L2. Не заменять другой моделью без согласования.
- **GigaAM** — необязательный ASR, независимый от детектора музыки. NCM — концептуальная аналогия coarse-to-fine, не обученный компонент SHSD.
- **L0–L3:** L0 — измеримые признаки и evidence; L1 — грубые события; L2 — подтверждённые детали и временные переходы; L3 — связное русское описание без неподтверждённых добавлений.
- **Temporal Event Memory:** стабильные event/claim IDs, интервалы в source time, PTS/time_base, epoch, ревизии, ссылки на evidence; отдельно фиксировать `observed`, `hypothesis`, `accepted_by_policy`, `human_verified`, `published`.
- **Поток:** bounded 600-секундный ring, очереди/backpressure, C/E/D/R watermarks и явные skipped/dropped intervals; L3 не блокирует ingest. Совпадение audio onset и video cut не означает причинную связь.
- **No-training production baseline:** текущие frozen веса не менять без разрешения. F10 параллельно изучает **обучаемый** projector/resampler между EmbeddingGemma 2 и Qwen3-0.6B; training experiment допускается после проверки интерфейса, данных, лицензий, CPU feasibility и bounded budget по уже полученному условному разрешению владельца. Малый независимый **оценочный** набор нужен уже сейчас.

Подробные исходные схемы API/JSONL/SQLite, контракты интервалов и watermarks — в [архивной v0.1 спецификации](docs/archive/2026-10-26-pre-multimodal-review/Workspace.md). При расхождении описания и реализации агент проверяет актуальный код, тесты и сообщает о несовместимости; не меняет контракт молча.

## 3. Зафиксированный baseline — не обещание качества

Контрольная точка: [commit 20acb747](https://github.com/aga7on/SHSD/commit/20acb74753adfd2315cd27c2e59052f6a4095b4c), 26.10.2026.

| Наблюдение | Результат | Интерпретация |
|---|---|---|
| 90 с `Tears of Steel`, file-mode, CPU 4 threads, 5-с окна | 62 L1, 108 L2, 3 русских L3; 55.16 с wall | **Не live realtime** |
| Положительный music multiclass probe | 4/18 accepted, все `conversation_dominant` | Coverage policy, **не accuracy** без ручных меток |
| L2 temporal refinement | 1 accepted music detail, 11 abstained, 96 skipped; 95 acoustic changes, 0 accepted semantic transitions | Акустическая новизна не доказывает музыкальные переходы |
| Деталь `percussion_present` в 01:10–01:25 | Accepted по текущей policy, но L1 этого события — `conversation_dominant`; Qwen её **не произнёс** | Проверить музыкальную предпосылку и доставку L2→L3 |
| 60 с 1x live Qwen v2 | Capture C=41.828/60 с, L1/L2 lag p50=22.270/17.733 с, 503 shared-prefetch drops, одна общая L3 | **Realtime не достигнут** |

Источники: [90s quality review](benchmarks/reports/music_multiclass_l2_20261026/real_video_quality_review.md), [music probe](benchmarks/reports/music_multiclass_l2_20261026/music_multiclass_probe.json), [60s live report](benchmarks/reports/live_qwen_v2_60s_20261026/report.md). Офлайн RTF, repeated-file warm cache и post-stop drain не подменяют pre-stop live coverage/lag.

**Исторические 157/159 пунктов F0–F6** означали закрытие прежнего плана, а не готовность системы и не прогресс нового backlog. Старый план архивирован.

## 4. P0: музыкальная предпосылка и публикация деталей

Разделить **возможность исследовать** музыкальную ось и **право утверждать** музыкальную деталь:

- `music_possible`: слабая/альтернативная гипотеза, достаточно для внутренних L2 probes; не является фактом для русского L3.
- `music_confirmed`: положительное свидетельство музыки, прошедшее согласованную policy и временную проверку; конкретная деталь дополнительно требует собственного evidence.
- `conversation_dominant` не равно «музыки нет» — фоновая музыка возможна. Но **одно присутствие `music_present` среди конкурирующих кандидатов с cosine≥0.60 не подтверждает музыку**.
- Если нет независимой подтверждённой музыкальной предпосылки, `percussion_present`/инструмент/бас/вокал можно оставить как непубликуемую гипотезу, но нельзя выдавать «в музыке слышны ударные» как подтверждённый факт.
- Нельзя просто снижать similarity/margin, чтобы увеличить accepted count. Любые изменения policy проверять на вручную размеченных positive/negative/overlap примерах.

Исходная точка риска: `src/shsd/semantic/temporal.py::_music_scene_supports_details`; обновить связанные `analyze.py`, claim schema и тесты.

## 5. P0: L2 → L3 — проверяемая доставка смысловых деталей

Сейчас `used_claim_ids` заполняются из **всех входных source IDs**, даже когда Qwen не выразил соответствующую деталь. Это не доказательство семантического покрытия.

Контракт следующего этапа: раздельно хранить `input_claim_ids`, `expressed_claim_ids`, `omitted_claim_ids` (и при необходимости `unverified_expression_ids`); формировать `expressed` **по фактическому тексту и проверке смыслового соответствия**, а не копированием входа. Политика salience/лимита токенов может позволять сознательные пропуски, но они должны быть наблюдаемыми и объяснимыми.

При подтверждённом музыкальном L2 L3 должен пытаться отразить значимую деталь по-русски. Если не отразил — записать omission, не считать claim использованным. Если текст приписывает неподтверждённый инструмент/действие — блокировать публикацию или source-only fallback с реальными ссылками. Лексическая проверка слов — лишь вспомогательная, не гарантия entailment.

## 6. P1: реальная временная музыка и визуальный смысл

**Музыка:** L2 сравнивает независимые соседние окна и state history, отличает продолжение слоя от onset/offset/перехода; DSP novelty — сигнал на проверку, не самостоятельный semantic claim. Проверять hard negatives (речь, шумы, монтаж) и overlap music+speech.

**Видео:** temporal identity и последовательность действий, grounded entity/action evidence. Визуальный cut может запускать проверку, но не заменяет «что произошло». Временные связи audio/video маркировать отдельно от причинных.

**Русский narrator:** несколько последовательных предложений при наличии подтверждённого содержания, меньше generic/dedup повторов, верные таймкоды и корректные revisions. Не стимулировать подробность за счёт hallucinations.

## 7. Критерии приёмки

1. **Качество:** независимые ручные метки (начать с 10–20 интервалов, затем расширять), заранее определённые precision/recall/abstention, false music premise, instrument/percussion false positives, transition precision, visual action/entity grounding, unsupported L3 claims и L2→L3 omissions. Результаты только с `N` и provenance; label-free probes не accuracy.
2. **Функция:** отдельные music exploration/publication states; явная traceability входных/произнесённых/пропущенных claims; тесты на conversation-only, music-only, music+speech и 01:10–01:25; сохранение CAS/revisions/watermarks.
3. **Live:** pre-stop 1x cold-cache на уникальном источнике, C/E/R coverage, lag p50/p95 и slope, drops, CPU/RSS, L3 latency и Qwen tok/s. Доказательство устойчивого `RTF ≤ 1` без растущего lag либо честный `not met`.
4. **Совместимость:** offline CPU, EmbeddingGemma 2 + Qwen3-0.6B, bounded ring, существующие API/JSONL/SQLite без неоговорённых breaking changes.

## 8. Параллельный F10: проверяем обучаемый EmbeddingGemma 2 → Qwen3-0.6B bridge

**Почему:** если frozen similarity matcher не извлекает действий, инструментов и временных связей, бесконечное расширение словаря гипотез может не решить задачу. Trainable alignment между аудио/видео представлениями и языковой моделью — серьёзная альтернатива, а не декоративный пункт.

**Гипотеза, не установленный факт:** небольшой projector/resampler и temporal fusion могут помочь Qwen строить последовательные grounded русские описания без обучения всей LLM. Однако **один pooled embedding** может потерять детали и время, а Qwen3-0.6B может не принимать произвольные prefix embeddings в целевом GGUF runtime. Сначала подтвердить доступные encoder tokens, LLM embedding API, latency и реальные права на данные.

**Сравнение:** frozen baseline A0/A2 vs обучаемый adapter B1 vs при необходимости B2 adapter+LoRA vs компактная готовая модель C; отдельно audio-only, video-only, AV, shuffled-time, swapped-audio, отсутствующая модальность, negatives и held-out sources. Успех измеряется не cosine, а factual visual story, музыкальными переходами, omissions/hallucinations и **1x CPU live**.

**Статус:** F10.01–F10.02 (исследование интерфейсов и проектирование) можно выполнять сейчас параллельно F7–F9. F10.03 (обучение) разрешено после technical/data/budget `GO`; F10.04 (LoRA, encoder/LLM fine-tuning, distillation или другие методы) разрешено при доказанной перспективности и отдельном ограниченном experimental budget; F10.05 — решение о production только после held-out и sustained 1x CPU live. Детали — [F10](Todo.md#f10--обучаемый-мультимодальный-мост-параллельный-rd-трек) и [план эксперимента](docs/experiments/bridge-training-pilot.md).

Исполнять [Todo.md](Todo.md). [ADR-002](docs/adr/ADR-002-multimodal-bridge-evaluation.md) — формальная рамка выбора; она принимает условное разрешение на обучение; production architecture не выбрана.


## Условное разрешение на R&D обучение — 26.10.2026

Владелец разрешил **любое обучение, если оно перспективно поможет решить главную боль**: содержательный, достоверный визуальный сюжет, подробные музыкальные слои/переходы и устойчивый CPU-only offline realtime. Это включает adapter/projector, LoRA, encoder/LLM fine-tuning, distillation и альтернативные модели. **Повторного согласования каждого эксперимента не требуется.**

**До GPU training:** (1) подтверждённый interface/conditioning и правдоподобный CPU deploy path; (2) права на данные и source-separated train/val/held-out; (3) зафиксированный baseline и независимые quality metrics; (4) bounded GPU budget, checkpoints и stop conditions; (5) письменный `F10-GO.md` с результатом `GO`. Если что-то не выполнено — `NO-GO`, не скрывать риск. После короткого пилота продолжать лишь при измеренном улучшении без роста ложных утверждений. В production новые веса попадут только после held-out A/B и sustained 1x CPU live. Это разрешение на исследование, **не доказательство, что обучение обязательно поможет**.

## 9. Порядок реализации после архитектурного анализа

**Инженерная рекомендация, не доказанный результат обучения:** исправить музыкальную предпосылку, L2→L3 claim accounting и live backlog; создать grounded temporal graph объектов, действий и музыкальных слоёв; сравнить B0 (graph→текстовый Qwen) с B1 (обучаемый bridge→Qwen). Если EmbeddingGemma не содержит нужных token/time-level фактов, сравнить специализированные visual action/audio music encoders, а не учить Qwen придумывать отсутствующие факты.

Обучение B1/LoRA/fine-tune разрешено владельцем **при документированном technical/data/CPU/budget GO**; не нужно повторно запрашивать разрешение. Нельзя объявлять GPU prototype production-ready без sustained CPU 1x. Последний Deep Research был остановлен до отчёта: конкретные API и численные улучшения остаются непроверенными до smoke tests. Следовать [F10 handoff](docs/experiments/F10-agent-handoff.md).
