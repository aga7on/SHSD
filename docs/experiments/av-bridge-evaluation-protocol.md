# SHSD — протокол проверки качества и CPU realtime

> 26.10.2026 · Рабочий evaluation protocol, не training plan. [Workspace](../../Workspace.md) · [Todo](../../Todo.md). Базовый commit: `20acb74753adfd2315cd27c2e59052f6a4095b4c`.

## 1. Набор источников и ручные метки

Начать с 10–20 независимо размеченных интервалов **разных источников**, расширять после пилота. Включить: speech-only, music-only, music+speech, environment-only, переходы ударных/баса/вокала, неизменный музыкальный слой, монтаж без смены инструмента, визуальное действие без смены кадра, audio/video swap, hard negatives. Отдельно проверить 01:10–01:25 `Tears of Steel`, где L2 выдал `percussion_present`, а L1 `conversation_dominant`.

Для каждой метки: `source_id`, лицензия/provenance, source interval, annotator, `music_presence`/overlap, независимые `percussion/bass/vocals/instrument_family`, onset/offset, visual entity/action, unknown и заметки о сомнении. **Не** использовать model scores как «ручные» метки. Аннотировать по возможности вслепую до просмотра outputs. Нельзя использовать один и тот же ролик как независимый held-out, если по нему подбирали prompts/thresholds.

## 2. Сравниваемые режимы

**B0** — grounded event graph → text-only Qwen; **B1** — тот же graph/evidence + learned multimodal conditioning. Не менять perception и narration одновременно без ablations. [F10 handoff](F10-agent-handoff.md).


- **A0:** `20acb747`, multiclass music L1, текущий temporal L2, Qwen L3.
- **A1:** A0 + отдельный music exploration/publication gate, независимое подтверждение premise, исправленный L2→L3 accounting.
- **A2:** A1 + temporal musical transitions и grounded visual action/entity memory.
- **C (только после A1/A2):** возможные специализированные CPU perception модели как независимые источники evidence, с теми же тестами.
- **B (F10, параллельный трек):** EmbeddingGemma 2→Qwen3-0.6B обучаемый bridge. Capability audit и дизайн выполнять сейчас; **фактическое обучение условно разрешено владельцем 26.10.2026** после documented technical/data/budget `GO`, лицензий, held-out и CPU deploy path. См. [pilot](bridge-training-pilot.md).

Для всех — одинаковые файлы, модельные ревизии, preprocessing, thresholds, windows, threads, Qwen settings. Разделять изменение policy и изменение perception.

## 3. Качество и ошибки

Считать `N` вручную размеченных окон/событий и per-axis TP/FP/FN/TN; precision/recall/F1 и accepted coverage/abstain. Для музыкальных деталей отдельно:

- `music_possible` как внутренний trigger **не** засчитывать опубликованным фактом;
- `music_confirmed` и `percussion_present` проверять **раздельно**;
- false-premise rate, false-detail rate, music+speech false negatives;
- onset/offset/semantic transitions — precision/recall с заранее зафиксированным tolerance; DSP novelty не считать ground truth;
- L3: `input_claim_ids`, `expressed_claim_ids`, `omitted_claim_ids`, unverifiable expressions, unsupported additions; paraphrases проверять семантически, не только по словам;
- visual: подтверждённые entity/action changes, temporal order, generic-caption rate, сюжетная связность и factual error taxonomy.

Human review русских captions проводить по blind source/timecodes; отметить независимость рецензента. Cosine и `accepted_by_policy` не являются accuracy. Нулевое количество принятых переходов может быть корректным при отсутствии истинных переходов.

## 4. CPU live (обязательный отдельный тест)

Сначала воспроизвести [60s live Qwen v2](../../benchmarks/reports/live_qwen_v2_60s_20261026/report.md): `ffmpeg -re` RTSP 1x, 4 CPU threads, 5s windows, Qwen, ASR off, 0 embedding cache hits. Старые факты: C=41.828/60 с, E=35.120 с, R[L1/L2/L3]=35.120/25.120/29.745 с; L1/L2 lag p50=22.27/17.73 с, 503 shared-prefetch drops, 1 общая L3.

Отдельно фиксировать:
- **pre-stop** source C/E/D/R, число полученных/обработанных/отброшенных окон и caption first-seen wall time;
- p50/p95/max и **slope** live lag, Qwen generation/prefill latency, CPU/RSS/threads, queue depths и drops по причинам;
- **post-stop drain** как другую метрику;
- cold unique-media и warm repeated-file как **разные** профили;
- sustained 1x, затем 2x/5x только при наличии аппаратных ресурсов и с честной degraded policy.

Цель: устойчивое 1x с `RTF ≤ 1`, нерастущим lag и без неучтённого покрытия. Если не достигнуто — отчёт `not met` с bottleneck; 55.16 с file analysis для 90 с источника **не** доказательство realtime.

## 5. Артефакты и решения

Писать `benchmarks/reports/music_quality_v2/` и `benchmarks/reports/live_cpu_v2/`: `manifest.json` (git/model revisions, CPU, source IDs, windows, configs), `labels.jsonl`, `claims.jsonl`, `captions.jsonl`, `metrics.json`, `errors.md`, `report.md` с точными командами запуска. Не коммитить чужие приватные медиа или персональные диалоги.

**Gate P0:** на independent labels нет опубликованных деталей с одной лишь слабой music premise; expressed/omitted claim IDs правдивы; ошибки и abstention измеримы. **Gate live:** sustained 1x подтверждён или явно `not met`. **Gate F10:** API+deployment smoke tests, conditional owner approval already recorded in ADR-002; technical/data/budget GO до training, независимые source-separated data, held-out A/B и CPU live. Дальнейшие архитектурные решения — по этим данным, а не по количеству чекбоксов.
