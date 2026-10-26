# Workspace.md — SHSD: текущая цель и архитектурная спецификация

> **Версия 0.6 · 26.10.2026 · статус: активный план улучшения качества и CPU realtime.**
> Исходная полная спецификация v0.1 сохранена [без изменений в архиве](docs/archive/2026-10-26-pre-multimodal-review/Workspace.md). Задачи — [Todo.md](Todo.md), правила — [Agents.md](Agents.md), протокол измерений — [docs/experiments/av-bridge-evaluation-protocol.md](docs/experiments/av-bridge-evaluation-protocol.md).
>
> **Практическое ТЗ:** [F10 coding-agent handoff](docs/experiments/F10-agent-handoff.md) · [AV event graph](docs/architecture/grounded-av-storytelling.md) · [F10-GO template](docs/experiments/F10-GO.template.md).
>
> **Граница:** целевой runtime остаётся offline/CPU-only. Существующая production-ветка пока training-free. **Обучаемый мультимодальный мост — отдельный параллельный R&D-трек F10 с конкретным протоколом**, а не отложенная заметка. **Владелец 26.10.2026 разрешил любое перспективное обучение** для улучшения grounded AV сюжета, музыки и temporal detail. Перед training — documented feasibility/data/budget `GO`, повторное разрешение не требуется.

## 1. Что строим

SHSD должен получать синхронизированные аудио и видео и с небольшой измеренной задержкой выдавать конкретное, проверяемое и связное русскоязычное описание. Важны четыре равноправные цели:

1. **Изображение и визуальный сюжет:** для IMAGE — видимые сущности, атрибуты и отношения; для VIDEO — устойчивость сущностей, действия и взаимодействия между кадрами, смены сцен и правильный временной порядок.
2. **Аудиосцена и музыкальная динамика:** речь, музыка и окружение, в том числе наложение; подтверждённые вокал, ударные, бас, семейства инструментов, появление/исчезновение слоёв и изменения во времени.
3. **Сшивка AV и русское повествование:** связывать визуальные и звуковые события по PTS и evidence, различать совпадение и причинность, передавать подтверждённые claims в связный L3 текст и явно учитывать пропуски и неопределённость.
4. **Своевременность:** обрабатывать уникальный 1x live источник без систематически растущего lag, потери покрытия и скрытого отбрасывания окон; 2x/5x — отдельные нагрузочные сценарии.

Успех в одной модальности не компенсирует провал в другой: отдельно принимать IMAGE, VIDEO, AUDIO и AV режимы. Всё, что нельзя подтвердить, помечать uncertain, unknown или abstained; не выдумывать точные инструменты, BPM, действия, причинность или сюжетные мотивы.

## 2. Сохраняемые решения и контракты

- **EmbeddingGemma 2** (`google/embeddinggemma-2`) — реальный мультимодальный encoder аудио/кадров/текста; эмбеддинги и их модельные ревизии, не прямые токены Qwen.
- **Qwen3-0.6B** — локальный CPU narrator для русского L3, работающий с обоснованными структурированными событиями L1/L2. Не заменять другой моделью без согласования.
- **GigaAM** — необязательный ASR, независимый от детектора музыки. NCM — концептуальная аналогия coarse-to-fine, не обученный компонент SHSD.
- **L0–L3:** L0 — измеримые признаки и evidence; L1 — грубые события; L2 — подтверждённые детали и временные переходы; L3 — связное русское описание без неподтверждённых добавлений.
- **Temporal Event Memory:** стабильные event/claim IDs, интервалы в source time, PTS/time_base, epoch, ревизии, ссылки на evidence; отдельно фиксировать `observed`, `hypothesis`, `accepted_by_policy`, `human_verified`, `published`.
- **Поток:** bounded 600-секундный ring, очереди/backpressure, C/E/D/R watermarks и явные skipped/dropped intervals; L3 не блокирует ingest. Совпадение audio onset и video cut не означает причинную связь.
- **No-training production baseline:** текущие frozen веса не менять без решения production gate. F10 — отдельный R&D трек Multimodal AV Bridge для grounded визуально-аудиального сюжетного описания, а не музыкальный тюнинг: IMAGE/VIDEO и AUDIO branches совместно поддерживают grounded events/claims и русское narration. Обучаемый projector/resampler допускается после проверки интерфейса, данных, лицензий, CPU feasibility и bounded budget по уже полученному условному разрешению владельца. Малый независимый оценочный набор нужен уже сейчас.

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

**Проверено на уровне интерфейсов, не качества:** EmbeddingGemma 2 отдаёт перед pooling sequence token embeddings для IMAGE/VIDEO/AUDIO/AV; четырёхтокенный внешний prefix ширины 1024 прошёл через реальный Qwen3-0.6B GGUF и llama.cpp CPU, после него прошёл обычный текстовый prefill и decode. Значения prefix были детерминированными probe-векторами — обучения и полезного conditioning не проверяли. Один pooled 768d вектор может потерять детали и время. `EmbeddingProvider` уже имеет opt-in sequence API с masks, token IDs и source PTS; `AVFeatureBatch` сохраняет отдельные IMAGE sequences по PTS и interval AUDIO. Опциональный review-importer добавляет проверенные visual action/music transition claims в EventGraph и Qwen-запросы; default `analyze` по-прежнему не потребляет sequence tokens и не извлекает визуальные сущности/действия автоматически. Изолированные VIDEO/AV вызовы заняли около 4 секунд на 5-секундном CPU fixture, поэтому суммарный audio+vision+fusion+Qwen режим 1x realtime не подтверждён.

**Сравнение:** frozen baseline A0/A2 vs обучаемый adapter B1 vs при необходимости B2 adapter+LoRA vs компактная готовая модель C; отдельно audio-only, video-only, AV, shuffled-time, swapped-audio, отсутствующая модальность, negatives и held-out sources. Успех измеряется не cosine, а factual visual story, музыкальными переходами, omissions/hallucinations и **1x CPU live**.

**Status:** F10.01 verified the CPU external-prefix path. The production EmbeddingProvider exposes opt-in sequence features, masks, token IDs, and source PTS for IMAGE/VIDEO/AUDIO/AV. `analyze` now builds a typed temporal claim graph from L2 revisions and uses it as the training-free B0 input to Qwen; this graph has no visual entity/action extraction and does not consume sequence tokens. See the [paired L1/L2/L3 review](benchmarks/reports/music_quality_v2/real_video_quality_review_b0_graph.md) and [cosine/margin diagnosis](benchmarks/reports/semantic_matcher_diagnostic_20261026/semantic_matcher_diagnostic.md).

**Приоритеты по проверке 27.10.2026:** P0 тесты `dataset.py`/`AVFeatureBatch`/EventGraph/action-scan окон и pixel-delta helper закрыты (274 unit tests passed; восемь F10 bridge/review test modules 75 passed), межманифестная проверка `source_group_id`/`source_id`/SHA закрыта. PTS-preserving sequence batches доходят до B0/EventGraph; импортёр сверяет serialized source PTS каждого кадра с `timeline_pts + offset`. Внешний X-CLIP даёт source-time action hypotheses, но в 13-окошечном скане сохраняет «встаёт с кровати» при снижающейся средней pixel difference и повышает logit до 12.98. Поэтому гипотезы не проверены человеком, не передаются Qwen и не встроены в default `analyze`. 90-секундный *Tears of Steel* L1/L2/L3 отчёт содержит все события и русские описания, но независимой разметки нет и L2 не принял новой музыкальной детали. AUDIO-only фрагмент 185–205с исходника содержит музыку перед сценой разговора; L1/L2/L3 фиксируют разговор с 190с, но не описывают музыкальный слой или его переход. B0 importer теперь может по `--narrate-qwen` запускать pinned CPU Qwen и сохранять реальные L3 captions с claim-coverage и fallback-статусом; запуск ждёт заполненную независимую разметку. Нужна проверка двух примеров: [отчёт и результаты](benchmarks/reports/bridge_f10/f10_03_semantic_candidates_20261027.md), [клипы, манифест и пустой шаблон меток](benchmarks/review/bridge_f10_examples/review_manifest.json), [blind review guide](benchmarks/review/bridge_f10_examples/review_guide.md), and [PTS validator](scripts/validate_f10_review_labels.py), [B0 importer](scripts/build_f10_reviewed_graphs.py). Текущий 27.10 live-прогон показал 41.8с захвата за 60с wall, 35.1с embedding coverage, 548 shared-prefetch drops и две Qwen-надписи с медианной задержкой 20.76с; 1x не выполнен. Полный отчёт: [F10.02 follow-up](benchmarks/reports/bridge_f10/f10_02_followup_20261027.md). B1 остаётся **NO-GO** до независимой оценки, лицензированных source-separated данных и ограниченного бюджета.

Исполнять [Todo.md](Todo.md). [ADR-002](docs/adr/ADR-002-multimodal-bridge-evaluation.md) — формальная рамка выбора; она принимает условное разрешение на обучение; production architecture не выбрана.


## Условное разрешение на R&D обучение — 26.10.2026

Владелец разрешил **любое обучение, если оно перспективно поможет решить главную боль**: содержательный, достоверный визуальный сюжет, подробные музыкальные слои/переходы и устойчивый CPU-only offline realtime. Это включает adapter/projector, LoRA, encoder/LLM fine-tuning, distillation и альтернативные модели. **Повторного согласования каждого эксперимента не требуется.**

**До GPU training:** (1) подтверждённый interface/conditioning и правдоподобный CPU deploy path; (2) права на данные и source-separated train/val/held-out; (3) зафиксированный baseline и независимые quality metrics; (4) bounded GPU budget, checkpoints и stop conditions; (5) письменный `F10-GO.md` с результатом `GO`. Если что-то не выполнено — `NO-GO`, не скрывать риск. После короткого пилота продолжать лишь при измеренном улучшении без роста ложных утверждений. В production новые веса попадут только после held-out A/B и sustained 1x CPU live. Это разрешение на исследование, **не доказательство, что обучение обязательно поможет**.

## 9. Порядок реализации после архитектурного анализа

**Engineering recommendation, not a learned result:** the typed temporal claim graph and B0 graph-to-accepted-facts-to-Qwen path are integrated. Frame-token PTS is preserved, and an external X-CLIP action candidate can be retained separately as an unverified graph hypothesis. Next obtain independent confirmation, improve music-layer transitions with real source-time evidence, and run same-source A0/B0. The current graph path does not improve perception by itself.

Обучение B1/LoRA/fine-tune разрешено владельцем **при документированном technical/data/CPU/budget GO**; не нужно повторно запрашивать разрешение. Нельзя объявлять GPU prototype production-ready без sustained CPU 1x. Предыдущий Deep Research был остановлен до отчёта; интерфейсные вопросы с тех пор проверены F10.01 smoke tests, но выигрыш качества и потоковая производительность не измерены. Следовать [F10 handoff](docs/experiments/F10-agent-handoff.md).


## F10 — исполняемое обучение IMAGE, VIDEO, AUDIO и AV

Обязательная спецификация: [F10-multimodal-training-design.md](docs/experiments/F10-multimodal-training-design.md). Проект обучает не только музыку: IMAGE — объекты и отношения на одном изображении; VIDEO — упорядоченные кадры, действия, отслеживание сущностей и последовательность событий; AUDIO — инструменты, музыкальные слои и переходы; AV — синхронизация визуальной истории и звука. Дизайн определяет FeatureBatch, два projector branches, временные и missing-modality masks, source-separated JSONL, CE по целевым токенам JSON+русского описания, начальные параметры обучения и раздельные проверки качества. Улучшение одной музыки без понимания изображений/видео не закрывает F10. Это проектная спецификация, а не измеренный результат.
