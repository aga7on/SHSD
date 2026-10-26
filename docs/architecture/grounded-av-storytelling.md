# Grounded AV storytelling — целевой контракт SHSD

> 26.10.2026. Дизайн, не реализованное состояние. Основан на текущих baseline и инженерных гипотезах, а не на завершённом Deep Research.

**Цель:** связный достоверный русский сюжет: кто/что видно, какое действие, взаимодействие, последовательность; параллельно — музыка, слои/инструменты, вокал/бас/ударные, onset/offset/переходы и наложение речи. Теги, cut и acoustic novelty — только сигналы, не готовая история.

## Путь данных

1. Ingest: source PTS/time_base, epoch, bounded 600s ring, C/E/D/R watermarks, explicit gaps/drops.
2. Visual evidence: sparse frames/cuts, tracked entities, действия и взаимодействия с интервалами.
3. Audio evidence: music/speech/ambience overlap, независимые music premise и music layer claims, DSP onset/offset as triggers.
4. L0–L2: temporal event graph, stable IDs, evidence refs, uncertainty, revisions.
5. A/B: B0 graph→compact grounded facts→Qwen3-0.6B; B1 graph+verified audio/video features→trainable projector/resampler→verified Qwen conditioning.
6. L3: проверка выраженных/пропущенных claims и unsupported additions; связный русский текст с правильным временным порядком.

## Проект типов (согласовать с существующим SQLite/JSONL/API)

| Тип | Поля | Ограничение |
|---|---|---|
| entity | entity_id, class, track evidence, interval | Не переносить identity без подтверждения |
| action | subject_id, verb, object_id?, interval, evidence | Cut не равен действию |
| scene_transition | from/to, PTS, evidence | Не выдумывать причину |
| audio_scene | speech/music/ambience, overlap, interval | Conversation-dominant не исключает music |
| music_layer | layer_id, family, onset/offset/change, evidence | Runner-up music не подтверждает percussion |
| av_relation | event IDs, temporal relation, evidence | Совпадение не причинность |
| caption_claim | input/expressed/omitted IDs, verifier state | Входной claim не обязательно произнесён |

Общие поля: source_id, epoch, PTS/time_base, evidence refs, model/preprocess revision, confidence_kind (cosine не вероятность), decision_state (observed/hypothesis/accepted_by_policy/human_verified/published), uncertainty reason, revision. Агент сохраняет CAS revisions, backward compatibility и bounded queues.

**Приёмка:** human-verified source-separated visual action/entity/order и music layer/transition precision/recall, unsupported L3 claims/omissions, RU coherence; sustained 1x unique-media CPU pre-stop C/E/R lag slope, drops, RSS. Negative controls: swapped audio, shuffled time, missing modality, speech-only, video cut without action.
