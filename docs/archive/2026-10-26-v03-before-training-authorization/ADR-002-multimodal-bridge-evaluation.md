# ADR-002 — Нужен ли SHSD обучаемый мультимодальный мост?

- **Status: Proposed / parallel R&D F10. Training is NOT approved yet.**
- Date: 2026-10-26
- Related: [ADR-001](ADR-001-next-version-performance.md), [Workspace](../../Workspace.md), [Todo](../../Todo.md), [evaluation protocol](../experiments/av-bridge-evaluation-protocol.md).

## Контекст

Цель SHSD — grounded русский сюжет и музыкальная динамика в CPU live. Замороженный EmbeddingGemma 2 + semantic/temporal matcher + Qwen3-0.6B уже работает, но на 90-секундном label-free фрагменте дал 3 преимущественно общих L3, 1 неподтверждённую вручную percussion detail и 0 принятых semantic transitions. 60-секундный cold-cache 1x live не успевал за источником. Проблемы могут быть в gating, слабом наборе гипотез, отсутствии fine-grained perception, temporal memory или доставке L2→L3; **из этих данных не следует, что нужно обучение**.

## Варианты для последующего решения

- **A (production baseline, параллельный поток):** frozen EmbeddingGemma 2 + DSP/при необходимости специализированные CPU detectors + независимые semantic axes + temporal event graph + Qwen3-0.6B. Исправлять premise gating, traceability, temporal transitions и live bottlenecks одновременно с исследованием B.
- **B (основной альтернативный эксперимент F10):** frozen EmbeddingGemma 2 и Qwen3-0.6B + **обучаемый** projector/resampler с token-level audio/video features и temporal conditioning, если они доступны; B2 — при необходимости дополнительный ограниченный LoRA. Нужны законные paired train data, source-separated held-out, реальный интерфейс Qwen `inputs_embeds` или эквивалент, и CPU deploy path. Планировать и проверять интерфейсы сейчас; запускать обучение только после одобрения.
- **C (исследование):** компактные pretrained VLM/audio-language или специализированные perception модели. Сравнивать русскую фактологичность, музыку, лицензии, offline CPU throughput и RAM.

Общее embedding-пространство **не является** готовым мультимодальным генератором. Pooled 768d vector может не сохранять инструменты/действия/порядок. PyTorch prototype не доказывает совместимость с Qwen GGUF/llama.cpp CPU runtime. Не заменять EmbeddingGemma/Qwen по умолчанию.

## Решение на сегодня

**Вести A и B параллельно как равноправные проверяемые гипотезы, но не смешивать их в production.** A — текущая frozen реализация, F7–F9; B — **активный R&D-трек F10** с проверкой реальных API, проектом training pilot, ablations и заранее определённым A/B. F10.01–02 разрешены сейчас и должны завершиться конкретным `go/no-go`. F10.03–05 описаны как этапы **возможного обучения и сравнения**, но фактический training пока запрещён до явного разрешения владельца. Детали: [bridge-training-pilot.md](../experiments/bridge-training-pilot.md).

## Условия, при которых можно предложить изменение решения

1. Независимые human labels и метрики A определены **до** training; необязательно ждать завершения всех F7–F9, чтобы спроектировать B.
2. Официально проверены hidden/token outputs encoder и Qwen prefix/CPU runtime; нет fake soft prompts.
3. Есть права на source-separated training corpus и held-out evaluation, ресурсы и точный план обучения.
4. Предварительный CPU budget, план квантования/деплоя и протокол sustained 1x сформированы; реальное соответствие latency будет проверяться на обученном checkpoint, а не предполагаться заранее.
5. Владелец проекта **явно одобрил новую ADR**, разрешающую обучение и изменение прежнего no-training ограничения.

**Разрешено сейчас:** F10.01–02, capability audit, shape/API smoke tests, дизайн и фиксация независимой оценки. **Не разрешено пока:** обучение projector/LoRA, сбор обучающего корпуса и замена production моделей. Эта ADR имеет статус Proposed и не отменяет [ADR-001](ADR-001-next-version-performance.md).
