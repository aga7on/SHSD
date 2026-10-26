# Реальный видео прогон: L1/L2/L3

Источник: `X:\AI\SHSD\benchmarks\fixtures\real_poc\tears_of_steel_120_210s.mp4`.
Длительность исходного фрагмента: 90 с; CPU, потоков: 4; окно: 5000 мс.
L3 backend: `qwen`.

## Результат прогона

- Событий L1: 62; событий L2: 62; русских L3 описаний: 3.
- L2 статусы: abstained — 11, confirmed — 1, skipped — 50.
- Новых деталей L2, принятых текущей policy: 0.
- L2 попыток, отложенных по нагрузке: 0; событий с итоговой L2-ревизией после backpressure: 0; без L2-ревизии: 0.
- Время анализа файла: 27.91 с (это офлайн полный прогон, не realtime-измерение).
- Кэш/инференс эмбеддингов по модальностям: audio: 18/18 cache hits, 0 ms inference; image: 7/7 cache hits, 0 ms inference.
- B0 event graph records: 1; unique event revisions: 62; unique start-order edges: 61; causal edges: 0.
- Неподдержанные новые утверждения Qwen: 0; fallbacks: 2.
- L2 отдельно записал 95 акустических изменений и 0 принятых semantic candidate transitions.

## P0: положительная многоклассовая диагностика

- Отчёт multiclass probe рядом с JSONL не найден.

## Диагностика semantic matcher

- 100 window matches: {'uncertain': 95, 'accepted': 5}; policy: cosine ≥ 0.6, margin ≥ 0.05; [подробный отчёт](../semantic_matcher_diagnostic_20261026/semantic_matcher_diagnostic.md).
- `music_presence`: n=18, decisions={'uncertain': 14, 'accepted': 4}, median cosine=0.761, median top-two margin=0.014; uncertain above cosine floor=14.
- `speech_presence`: n=18, decisions={'uncertain': 17, 'accepted': 1}, median cosine=0.734, median top-two margin=0.011; uncertain above cosine floor=17.
- Это label-free сравнение эмбеддингов, не ручная оценка точности; cosine нельзя читать как вероятность.

Новая деталь L2, принятая текущей policy (без ручной проверки):

- Нет.

## L1 события

| Начало | Конец | Тип | Статус | ID | Русские claims (решение; cosine; label) |
|---:|---:|---|---|---|---|
| 00:00.00 | 00:10.00 | unknown | committed | 2ee93a0a | В аудио преобладают звуки окружающей среды и повседневные шумы. [uncertain; cosine=0.756; environment_dominant] |
| 00:00.00 | 00:10.00 | unknown | committed | c528cc16 | В аудио не слышно речи человека. [uncertain; cosine=0.729; speech_absent] |
| 00:00.00 | 00:25.00 | unknown | committed | 5b8a4f43 | unknown [uncertain; cosine=0.582; unknown] |
| 00:00.00 | 00:25.00 | unknown | committed | 81bad62f | На изображении виден человек. [uncertain; cosine=0.623; person_visible] |
| 00:00.00 | 01:30.00 | unknown | committed | b7f8c089 | Слышен непрерывный фоновый звук окружающей среды. [uncertain; cosine=0.758; ambient_sound_present] |
| 00:00.00 | 01:30.00 | unknown | committed | e15aadf0 | Слышен один или несколько коротких ударных звуков. [uncertain; cosine=0.750; impact_present] |
| 00:01.00 | 00:02.00 | cross_modal_coincidence | committed | 4b9d3520 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:02.00 | 00:03.00 | cross_modal_coincidence | committed | 42020f0e | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:03.00 | 00:04.01 | cross_modal_coincidence | committed | b11c8348 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:04.00 | 00:05.00 | cross_modal_coincidence | committed | c6865f8c | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:05.00 | 00:06.03 | cross_modal_coincidence | committed | 812bd7cb | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:05.00 | 00:25.00 | unknown | committed | e409d071 | На изображении показано помещение. [uncertain; cosine=0.635; indoor_setting] |
| 00:06.00 | 00:07.01 | cross_modal_coincidence | committed | 935d8578 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:07.00 | 00:08.00 | cross_modal_coincidence | committed | ab41a138 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:10.00 | 00:20.00 | unknown | committed | eff78f4f | В аудио слышна речь человека. [uncertain; cosine=0.743; speech_present] |
| 00:10.00 | 00:25.00 | unknown | committed | f9375fe4 | unknown [uncertain; cosine=0.594; unknown] |
| 00:14.00 | 00:15.05 | cross_modal_coincidence | committed | ae4c43dd | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:19.00 | 00:20.11 | cross_modal_coincidence | committed | d96826a8 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:20.00 | 00:30.00 | unknown | committed | a932edc7 | В аудио не слышно речи человека. [uncertain; cosine=0.729; speech_absent] |
| 00:20.00 | 00:55.00 | unknown | committed | 670af201 | Музыка звучит на первом плане и преобладает в аудио. [uncertain; cosine=0.773; music_present] |
| 00:23.00 | 00:24.05 | cross_modal_coincidence | committed | 3ffc4873 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:25.00 | 00:26.02 | cross_modal_coincidence | committed | be7db278 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:32.00 | 00:33.05 | cross_modal_coincidence | committed | 5d2664ad | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:35.00 | 00:55.00 | unknown | committed | f682148f | В аудио не слышно речи человека. [uncertain; cosine=0.732; speech_absent] |
| 00:38.00 | 00:39.05 | cross_modal_coincidence | committed | 47a9e59a | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:39.00 | 00:40.08 | cross_modal_coincidence | committed | 34758fd9 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:40.00 | 00:41.00 | cross_modal_coincidence | committed | 3222b369 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:41.00 | 00:42.00 | cross_modal_coincidence | committed | a4a1c230 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:42.00 | 00:43.00 | cross_modal_coincidence | committed | ba287a61 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:43.00 | 00:44.00 | cross_modal_coincidence | committed | 54821148 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:44.00 | 00:45.00 | cross_modal_coincidence | committed | 3ed039a2 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:45.00 | 00:46.00 | cross_modal_coincidence | committed | 3c285504 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:46.00 | 00:47.00 | cross_modal_coincidence | committed | 16a84590 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:47.00 | 00:48.09 | cross_modal_coincidence | committed | 120fedde | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:48.00 | 00:49.02 | cross_modal_coincidence | committed | 5f3ccbd3 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:51.00 | 00:52.00 | cross_modal_coincidence | committed | d5be7f24 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:52.00 | 00:53.01 | cross_modal_coincidence | committed | 279be810 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:54.00 | 00:55.00 | cross_modal_coincidence | committed | aefab58b | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:55.00 | 00:56.01 | cross_modal_coincidence | committed | 9f685623 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:55.00 | 01:05.00 | unknown | committed | c2b1ed87 | В аудио слышна речь человека. [uncertain; cosine=0.763; speech_present] |
| 00:56.00 | 00:57.09 | cross_modal_coincidence | committed | aa1785b4 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:57.00 | 00:58.00 | cross_modal_coincidence | committed | 373d9d74 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:00.00 | 01:01.09 | cross_modal_coincidence | committed | 7c56c28f | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:00.00 | 01:10.00 | unknown | committed | 9c5c911b | Музыка звучит на первом плане и преобладает в аудио. [uncertain; cosine=0.786; music_present] |
| 01:01.00 | 01:02.05 | cross_modal_coincidence | committed | 0824f88d | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:03.00 | 01:04.00 | cross_modal_coincidence | committed | a5eeafab | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:09.00 | 01:10.00 | cross_modal_coincidence | committed | d5123bab | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:10.00 | 01:25.00 | audio_scene_changed | committed | 2bc1fb53 | На первом плане слышен разговор людей. [accepted; cosine=0.747; conversation_dominant] |
| 01:12.00 | 01:13.06 | cross_modal_coincidence | committed | 112b80c6 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:13.00 | 01:14.00 | cross_modal_coincidence | committed | e762485f | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:15.00 | 01:30.00 | unknown | committed | 23cf9022 | В аудио слышна речь человека. [uncertain; cosine=0.727; speech_present] |
| 01:16.00 | 01:17.00 | cross_modal_coincidence | committed | b6210395 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:17.00 | 01:18.02 | cross_modal_coincidence | committed | 7174c5d7 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:18.00 | 01:19.05 | cross_modal_coincidence | committed | 71c059b7 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:20.00 | 01:21.00 | cross_modal_coincidence | committed | bdafeaa6 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:21.00 | 01:22.02 | cross_modal_coincidence | committed | ddf91e1d | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:23.00 | 01:24.06 | cross_modal_coincidence | committed | a39b3312 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:24.00 | 01:25.00 | cross_modal_coincidence | committed | 324594cd | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:25.00 | 01:26.00 | cross_modal_coincidence | committed | ce158ab7 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:26.00 | 01:27.00 | cross_modal_coincidence | committed | 55d036a7 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:27.00 | 01:28.02 | cross_modal_coincidence | committed | d59f4855 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:28.00 | 01:29.00 | cross_modal_coincidence | committed | c03f609a | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |

## L2 события

| Начало | Конец | Тип | Статус | ID | Русские claims (решение; cosine; label) |
|---:|---:|---|---|---|---|
| 00:00.00 | 00:10.00 | unknown | committed | 2ee93a0a | В аудио преобладают звуки окружающей среды и повседневные шумы. [uncertain; cosine=0.756; environment_dominant] |
| 00:00.00 | 00:10.00 | unknown | committed | c528cc16 | В аудио не слышно речи человека. [uncertain; cosine=0.729; speech_absent] |
| 00:00.00 | 00:25.00 | unknown | committed | 5b8a4f43 | unknown [uncertain; cosine=0.582; unknown] |
| 00:00.00 | 00:25.00 | unknown | committed | 81bad62f | На изображении виден человек. [uncertain; cosine=0.623; person_visible] |
| 00:00.00 | 01:30.00 | unknown | committed | b7f8c089 | Слышен непрерывный фоновый звук окружающей среды. [uncertain; cosine=0.758; ambient_sound_present] |
| 00:00.00 | 01:30.00 | unknown | committed | e15aadf0 | Слышен один или несколько коротких ударных звуков. [uncertain; cosine=0.750; impact_present] |
| 00:01.00 | 00:02.00 | cross_modal_coincidence | committed | 4b9d3520 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:02.00 | 00:03.00 | cross_modal_coincidence | committed | 42020f0e | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:03.00 | 00:04.01 | cross_modal_coincidence | committed | b11c8348 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:04.00 | 00:05.00 | cross_modal_coincidence | committed | c6865f8c | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:05.00 | 00:06.03 | cross_modal_coincidence | committed | 812bd7cb | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:05.00 | 00:25.00 | unknown | committed | e409d071 | На изображении показано помещение. [uncertain; cosine=0.635; indoor_setting] |
| 00:06.00 | 00:07.01 | cross_modal_coincidence | committed | 935d8578 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:07.00 | 00:08.00 | cross_modal_coincidence | committed | ab41a138 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:10.00 | 00:20.00 | unknown | committed | eff78f4f | В аудио слышна речь человека. [uncertain; cosine=0.743; speech_present] |
| 00:10.00 | 00:25.00 | unknown | committed | f9375fe4 | unknown [uncertain; cosine=0.594; unknown] |
| 00:14.00 | 00:15.05 | cross_modal_coincidence | committed | ae4c43dd | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:19.00 | 00:20.11 | cross_modal_coincidence | committed | d96826a8 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:20.00 | 00:30.00 | unknown | committed | a932edc7 | В аудио не слышно речи человека. [uncertain; cosine=0.729; speech_absent] |
| 00:20.00 | 00:55.00 | unknown | committed | 670af201 | Музыка звучит на первом плане и преобладает в аудио. [uncertain; cosine=0.773; music_present] |
| 00:23.00 | 00:24.05 | cross_modal_coincidence | committed | 3ffc4873 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:25.00 | 00:26.02 | cross_modal_coincidence | committed | be7db278 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:32.00 | 00:33.05 | cross_modal_coincidence | committed | 5d2664ad | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:35.00 | 00:55.00 | unknown | committed | f682148f | В аудио не слышно речи человека. [uncertain; cosine=0.732; speech_absent] |
| 00:38.00 | 00:39.05 | cross_modal_coincidence | committed | 47a9e59a | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:39.00 | 00:40.08 | cross_modal_coincidence | committed | 34758fd9 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:40.00 | 00:41.00 | cross_modal_coincidence | committed | 3222b369 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:41.00 | 00:42.00 | cross_modal_coincidence | committed | a4a1c230 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:42.00 | 00:43.00 | cross_modal_coincidence | committed | ba287a61 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:43.00 | 00:44.00 | cross_modal_coincidence | committed | 54821148 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:44.00 | 00:45.00 | cross_modal_coincidence | committed | 3ed039a2 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:45.00 | 00:46.00 | cross_modal_coincidence | committed | 3c285504 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:46.00 | 00:47.00 | cross_modal_coincidence | committed | 16a84590 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:47.00 | 00:48.09 | cross_modal_coincidence | committed | 120fedde | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:48.00 | 00:49.02 | cross_modal_coincidence | committed | 5f3ccbd3 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:51.00 | 00:52.00 | cross_modal_coincidence | committed | d5be7f24 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:52.00 | 00:53.01 | cross_modal_coincidence | committed | 279be810 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:54.00 | 00:55.00 | cross_modal_coincidence | committed | aefab58b | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:55.00 | 00:56.01 | cross_modal_coincidence | committed | 9f685623 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:55.00 | 01:05.00 | unknown | committed | c2b1ed87 | В аудио слышна речь человека. [uncertain; cosine=0.763; speech_present] |
| 00:56.00 | 00:57.09 | cross_modal_coincidence | committed | aa1785b4 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:57.00 | 00:58.00 | cross_modal_coincidence | committed | 373d9d74 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:00.00 | 01:01.09 | cross_modal_coincidence | committed | 7c56c28f | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:00.00 | 01:10.00 | unknown | committed | 9c5c911b | Музыка звучит на первом плане и преобладает в аудио. [uncertain; cosine=0.786; music_present] |
| 01:01.00 | 01:02.05 | cross_modal_coincidence | committed | 0824f88d | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:03.00 | 01:04.00 | cross_modal_coincidence | committed | a5eeafab | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:09.00 | 01:10.00 | cross_modal_coincidence | committed | d5123bab | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:10.00 | 01:25.00 | audio_scene_changed | refined | 2bc1fb53 | На первом плане слышен разговор людей. [accepted; cosine=0.809; conversation_dominant] |
| 01:12.00 | 01:13.06 | cross_modal_coincidence | committed | 112b80c6 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:13.00 | 01:14.00 | cross_modal_coincidence | committed | e762485f | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:15.00 | 01:30.00 | unknown | committed | 23cf9022 | В аудио слышна речь человека. [uncertain; cosine=0.727; speech_present] |
| 01:16.00 | 01:17.00 | cross_modal_coincidence | committed | b6210395 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:17.00 | 01:18.02 | cross_modal_coincidence | committed | 7174c5d7 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:18.00 | 01:19.05 | cross_modal_coincidence | committed | 71c059b7 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:20.00 | 01:21.00 | cross_modal_coincidence | committed | bdafeaa6 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:21.00 | 01:22.02 | cross_modal_coincidence | committed | ddf91e1d | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:23.00 | 01:24.06 | cross_modal_coincidence | committed | a39b3312 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:24.00 | 01:25.00 | cross_modal_coincidence | committed | 324594cd | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:25.00 | 01:26.00 | cross_modal_coincidence | committed | ce158ab7 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:26.00 | 01:27.00 | cross_modal_coincidence | committed | 55d036a7 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:27.00 | 01:28.02 | cross_modal_coincidence | committed | d59f4855 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:28.00 | 01:29.00 | cross_modal_coincidence | committed | c03f609a | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |

## L3 описания Qwen

| Интервал | Русское описание | Время генерации | Источники |
|---|---|---:|---|
| 00:01.00–00:04.01 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 3132 мс | 4b9d3520, 42020f0e, b11c8348 |
| 01:10.00–01:25.00 | На первом плане слышен разговор. | 3467 мс | 2bc1fb53, 112b80c6, e762485f |
| 01:16.00–01:19.05 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 3064 мс | b6210395, 7174c5d7, 71c059b7 |

## Ограничения оценки

- В этом репозитории нет независимых ручных музыкальных меток для этих интервалов. Поэтому повышение cosine/числа подтверждений не доказывает точность и отсутствие FP.
- Cosine similarity — оценка сходства текста и эмбеддинга, а не вероятность.
- Qwen и L2 здесь запускались после чтения локального файла; задержки не описывают непрерывную live обработку.
- Веса моделей не изменялись.

## Тайминги стадий офлайн прогона

Эти значения суммарные; стадии частично перекрываются и их нельзя складывать в задержку одного события.

- `audio_consumer_work`: 381.7 мс.
- `embedding_inference`: 0.0 мс.
- `embedding_model_and_text_profiles`: 10617.5 мс.
- `embedding_result_apply`: 2.8 мс.
- `embedding_worker_elapsed`: 200.7 мс.
- `l1_match_and_reduce`: 459.6 мс.
- `l2_state_refinement`: 117.6 мс.
- `l3_narration`: 10277.3 мс.
- `shared_media_interleave`: 6779.2 мс.
- `video_consumer_work`: 739.9 мс.
