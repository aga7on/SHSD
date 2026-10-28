# ADR-002 — Нужен ли SHSD обучаемый мультимодальный мост?

- **Status: Accepted for conditional training R&D (2026-10-26); production choice undecided.**
- Date: 2026-10-26
- Related: [ADR-001](ADR-001-next-version-performance.md), [Workspace](../../Workspace.md), [Todo](../../Todo.md), [evaluation protocol](../experiments/av-bridge-evaluation-protocol.md).

## Контекст

Цель SHSD — grounded русский сюжет и музыкальная динамика в CPU live. Замороженный EmbeddingGemma 2 + semantic/temporal matcher + Qwen3-0.6B уже работает, но на 90-секундном label-free фрагменте дал 3 преимущественно общих L3, 1 неподтверждённую вручную percussion detail и 0 принятых semantic transitions. 60-секундный cold-cache 1x live не успевал за источником. Проблемы могут быть в gating, слабом наборе гипотез, отсутствии fine-grained perception, temporal memory или доставке L2→L3; **из этих данных не следует, что нужно обучение**.

## Варианты для последующего решения

- **A (production baseline, параллельный поток):** frozen EmbeddingGemma 2 + DSP/при необходимости специализированные CPU detectors + независимые semantic axes + temporal event graph + Qwen3-0.6B. Исправлять premise gating, traceability, temporal transitions и live bottlenecks одновременно с исследованием B.
- **B (основной альтернативный эксперимент F10):** frozen EmbeddingGemma 2 и Qwen3-0.6B + **обучаемый** projector/resampler с token-level audio/video features и temporal conditioning, если они доступны; B2 — при необходимости дополнительный ограниченный LoRA. Нужны законные paired train data, source-separated held-out, реальный интерфейс Qwen `inputs_embeds` или эквивалент, и CPU deploy path. Планировать и проверять интерфейсы сейчас; запускать обучение после документированного technical/data/budget `GO` по уже полученному условному разрешению.
- **C (исследование):** компактные pretrained VLM/audio-language или специализированные perception модели. Сравнивать русскую фактологичность, музыку, лицензии, offline CPU throughput и RAM.

Общее embedding-пространство **не является** готовым мультимодальным генератором. Pooled 768d vector может не сохранять инструменты/действия/порядок. PyTorch prototype не доказывает совместимость с Qwen GGUF/llama.cpp CPU runtime. Не заменять EmbeddingGemma/Qwen по умолчанию.

## Gate перспективности

Общее embedding-пространство не означает способности строить визуальный сюжет или музыкальные переходы. До обучения подтвердить доступные audio/video features, Qwen non-text conditioning и CPU deploy path; легальные source-separated данные; независимые visual/music quality metrics и ограниченный budget. B1 small projector — первый пилот; B2 LoRA/глубокое обучение — только при подтверждённой перспективности. Если pooled EmbeddingGemma теряет действия/инструменты, сравнить независимые perception models. [F10 handoff](../experiments/F10-agent-handoff.md) · [GO template](../experiments/F10-GO.template.md).

## Решение на сегодня

**Вести A и B параллельно как равноправные проверяемые гипотезы, но не смешивать их в production.** A — текущая frozen реализация, F7–F9; B — **активный R&D-трек F10** с проверкой реальных API, проектом training pilot, ablations и заранее определённым A/B. F10.01–02 разрешены сейчас и должны завершиться конкретным `go/no-go`. F10.03–05 описаны как этапы **возможного обучения и сравнения**, но фактический training разрешён после technical/data/budget `GO`, без повторного разрешения владельца. Детали: [bridge-training-pilot.md](../experiments/bridge-training-pilot.md).

## Условия, при которых можно предложить изменение решения

1. Независимые human labels и метрики A определены **до** training; необязательно ждать завершения всех F7–F9, чтобы спроектировать B.
2. Официально проверены hidden/token outputs encoder и Qwen prefix/CPU runtime; нет fake soft prompts.
3. Есть права на source-separated training corpus и held-out evaluation, ресурсы и точный план обучения.
4. Предварительный CPU budget, план квантования/деплоя и протокол sustained 1x сформированы; реальное соответствие latency будет проверяться на обученном checkpoint, а не предполагаться заранее.
5. **Владелец проекта 26.10.2026 явно разрешил любое обучение, если оно перспективно помогает решить главную проблему.** Это включает projector, LoRA, encoder/LLM fine-tuning, distillation и альтернативы при обоснованной гипотезе, проверке данных, CPU deployment path и ограниченном бюджете; повторное разрешение не требуется.

**Разрешено сейчас:** F10.01–02, capability audit, shape/API smoke tests, дизайн и фиксация независимой оценки. **Разрешено условно:** обучение projector/LoRA/других моделей и подготовка законного корпуса после documented technical/data/budget `GO`. **Не разрешена автоматически:** замена production без независимой проверки качества и CPU realtime. Эта ADR имеет статус Accepted for conditional R&D training и не отменяет [ADR-001](ADR-001-next-version-performance.md).


## Условное разрешение на R&D обучение — 26.10.2026

Владелец разрешил **любое обучение, если оно перспективно поможет решить главную боль**: содержательный, достоверный визуальный сюжет, подробные музыкальные слои/переходы и устойчивый CPU-only offline realtime. Это включает adapter/projector, LoRA, encoder/LLM fine-tuning, distillation и альтернативные модели. **Повторного согласования каждого эксперимента не требуется.**

**До GPU training:** (1) подтверждённый interface/conditioning и правдоподобный CPU deploy path; (2) права на данные и source-separated train/val/held-out; (3) зафиксированный baseline и независимые quality metrics; (4) bounded GPU budget, checkpoints и stop conditions; (5) письменный `F10-GO.md` с результатом `GO`. Если что-то не выполнено — `NO-GO`, не скрывать риск. После короткого пилота продолжать лишь при измеренном улучшении без роста ложных утверждений. В production новые веса попадут только после held-out A/B и sustained 1x CPU live. Это разрешение на исследование, **не доказательство, что обучение обязательно поможет**.


## Полная мультимодальность вместо music-only

Разрешённый при technical/data/budget GO обучаемый эксперимент B1 обязательно рассматривает IMAGE, VIDEO, AUDIO и AV. Vision projector принимает отдельное изображение и упорядоченную серию кадров с PTS, audio projector принимает музыкальные и звуковые интервалы; temporal fusion должен сохранять визуальный сюжет и аудиопереходы. Обязательные самостоятельные image/video метрики и training details: [F10 training design](../experiments/F10-multimodal-training-design.md). Успех музыкальных тегов при неработающем видеосюжете не является положительным решением ADR.
