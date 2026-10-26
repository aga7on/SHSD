# ADR-002 — Нужен ли SHSD обучаемый мультимодальный мост?

- **Status: Proposed / research-only. Training is NOT approved.**
- Date: 2026-10-26
- Related: [ADR-001](ADR-001-next-version-performance.md), [Workspace](../../Workspace.md), [Todo](../../Todo.md), [evaluation protocol](../experiments/av-bridge-evaluation-protocol.md).

## Контекст

Цель SHSD — grounded русский сюжет и музыкальная динамика в CPU live. Замороженный EmbeddingGemma 2 + semantic/temporal matcher + Qwen3-0.6B уже работает, но на 90-секундном label-free фрагменте дал 3 преимущественно общих L3, 1 неподтверждённую вручную percussion detail и 0 принятых semantic transitions. 60-секундный cold-cache 1x live не успевал за источником. Проблемы могут быть в gating, слабом наборе гипотез, отсутствии fine-grained perception, temporal memory или доставке L2→L3; **из этих данных не следует, что нужно обучение**.

## Варианты для последующего решения

- **A (текущий обязательный baseline):** frozen EmbeddingGemma 2 + DSP/при необходимости специализированные CPU detectors + независимые semantic axes + temporal event graph + Qwen3-0.6B. Исправить premise gating, traceability, temporal transitions и live bottlenecks **сначала**.
- **B (исследование, не разрешённая реализация):** замороженные encoder и Qwen + небольшой **обученный** projector/resampler; потенциально audio/video patch/time-level features и temporal prefix. Требуются парные законные train data, независимый held-out и реальный интерфейс Qwen `inputs_embeds` или эквивалент.
- **C (исследование):** компактные pretrained VLM/audio-language или специализированные perception модели. Сравнивать русскую фактологичность, музыку, лицензии, offline CPU throughput и RAM.

Общее embedding-пространство **не является** готовым мультимодальным генератором. Pooled 768d vector может не сохранять инструменты/действия/порядок. PyTorch prototype не доказывает совместимость с Qwen GGUF/llama.cpp CPU runtime. Не заменять EmbeddingGemma/Qwen по умолчанию.

## Решение на сегодня

**Оставить A и запрет обучения действующими.** Исполнить F7.01–04, F8.01–02, F9.01. Допускается **документальный** capability audit B/C без обучения и без добавления production dependencies.

## Условия, при которых можно предложить изменение решения

1. Независимые human labels доказывают существенный предел качества frozen A на визуальных действиях/музыке, не устранимый дешёвыми features или event graph.
2. Официально проверены hidden/token outputs encoder и Qwen prefix/CPU runtime; нет fake soft prompts.
3. Есть права на source-separated training corpus и held-out evaluation, ресурсы и точный план обучения.
4. Предварительный CPU budget показывает возможность sustained 1x с ограниченным lag.
5. Владелец проекта **явно одобрил новую ADR**, разрешающую обучение и изменение прежнего no-training ограничения.

До выполнения всех условий **никакого projector training, LoRA, encoder fine-tuning или distillation**. Эта ADR имеет статус Proposed и не отменяет [ADR-001](ADR-001-next-version-performance.md).
