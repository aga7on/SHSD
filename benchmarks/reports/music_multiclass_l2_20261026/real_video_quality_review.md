# Реальный видео прогон: L1/L2/L3

Источник: `X:\AI\SHSD\benchmarks\fixtures\real_poc\tears_of_steel_120_210s.mp4`.
Длительность исходного фрагмента: 90 с; CPU, потоков: 4; окно: 5000 мс.
L3 backend: `qwen`.

## Результат прогона

- Событий L1: 62; событий L2: 108; русских L3 описаний: 3.
- L2 статусы: abstained — 11, confirmed — 1, skipped — 96.
- Новых деталей L2, принятых текущей policy: 1.
- L2 попыток, отложенных по нагрузке: 1; событий с итоговой L2-ревизией после backpressure: 1; без L2-ревизии: 0.
- Время анализа файла: 55.16 с (это офлайн полный прогон, не realtime-измерение).
- Неподдержанные новые утверждения Qwen: 0; fallbacks: 0.
- L2 отдельно записал 95 акустических изменений и 0 принятых semantic candidate transitions.

## P0: положительная многоклассовая диагностика

- Положительный 4-классовый probe: 4/18 принятых решений против 0/18 у старой бинарной пары.
- Все принятые классы: conversation_dominant: 4.
- Top-класс по окнам: conversation_dominant: 6, environment_dominant: 3, music_present: 9.
- У сцены средний лучший cosine=0.764 (min/max 0.728/0.796), а средний отрыв первого кандидата от второго=0.026 (min/max 0.004/0.082) при policy similarity=0.60, margin=0.05. Высокое сходство само по себе не снимает abstain, если кандидаты близки.
- Неутверждённые top-rank переходы между окнами: 00:10.00 environment_dominant → conversation_dominant; 00:20.00 conversation_dominant → music_present; 00:55.00 music_present → environment_dominant; 01:00.00 environment_dominant → music_present; 01:10.00 music_present → conversation_dominant.
- Диагностические принятые кандидаты по независимым осям, до L2 временной проверки:

| Ось | Средний лучший cosine | Margin min/mean/max | Принято / окон | Принятые кандидаты |
|---|---:|---:|---:|---|
| `bass_presence` | 0.720 | 0.000/0.009/0.039 | 0/18 | нет |
| `electronic_timbre` | 0.729 | 0.003/0.023/0.060 | 1/18 | electronic_timbre_present: 1 |
| `energy` | 0.736 | 0.004/0.029/0.081 | 2/18 | high_energy: 1, low_energy: 1 |
| `instrument_family` | 0.719 | 0.000/0.005/0.016 | 0/18 | нет |
| `music_presence` | 0.764 | 0.004/0.026/0.082 | 4/18 | conversation_dominant: 4 |
| `percussion_presence` | 0.730 | 0.001/0.023/0.071 | 3/18 | percussion_present: 3 |
| `tempo_feel` | 0.733 | 0.000/0.015/0.040 | 0/18 | нет |
| `vocal_presence` | 0.736 | 0.013/0.029/0.069 | 2/18 | vocals_present: 2 |
- Это label-free сравнение эмбеддингов, не ручная оценка точности; cosine нельзя читать как вероятность.

Новая деталь L2, принятая текущей policy (без ручной проверки):

- В музыке отчётливо слышен ритм ударных. (cosine=0.737; audio:75000-80000, audio:80000-85000, embedding:audio:914f7f89142e:0c31025ee91512327562, embedding:audio:914f7f89142e:35579f5e88bc656c2ddf, signal-summary:audio:914f7f89142e:0c31025ee91512327562, signal-summary:audio:914f7f89142e:35579f5e88bc656c2ddf, axis:percussion_presence, l2:coarse-to-fine:db7693c51ca947568102d8a44f3d24c3; event `db7693c5`).

## L1 события

| Начало | Конец | Тип | Статус | ID | Русские claims (решение; cosine; label) |
|---:|---:|---|---|---|---|
| 00:00.00 | 00:10.00 | unknown | committed | 207caff0 | В аудио преобладают звуки окружающей среды и повседневные шумы. [uncertain; cosine=0.756; environment_dominant] |
| 00:00.00 | 00:10.00 | unknown | committed | 70b7558b | unknown [uncertain; cosine=0.583; unknown] |
| 00:00.00 | 00:10.00 | unknown | committed | 94f7612b | В аудио не слышно речи человека. [uncertain; cosine=0.729; speech_absent] |
| 00:00.00 | 00:10.00 | unknown | committed | fd465b80 | На изображении виден человек. [uncertain; cosine=0.622; person_visible] |
| 00:00.00 | 01:30.00 | unknown | committed | 075c1be3 | Слышен один или несколько коротких ударных звуков. [uncertain; cosine=0.750; impact_present] |
| 00:00.00 | 01:30.00 | unknown | committed | 937f1583 | Слышен непрерывный фоновый звук окружающей среды. [uncertain; cosine=0.758; ambient_sound_present] |
| 00:01.00 | 00:02.00 | cross_modal_coincidence | committed | a1386ef0 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:02.00 | 00:03.00 | cross_modal_coincidence | committed | da2b587b | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:03.00 | 00:04.01 | cross_modal_coincidence | committed | 54261b5e | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:04.00 | 00:05.00 | cross_modal_coincidence | committed | d41f8d6f | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:05.00 | 00:06.03 | cross_modal_coincidence | committed | 833c8cfe | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:06.00 | 00:07.01 | cross_modal_coincidence | committed | 266657be | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:07.00 | 00:08.00 | cross_modal_coincidence | committed | 0d63901c | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:10.00 | 00:20.00 | unknown | committed | cc4cead6 | В аудио слышна речь человека. [uncertain; cosine=0.743; speech_present] |
| 00:14.00 | 00:15.05 | cross_modal_coincidence | committed | 69328a96 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:19.00 | 00:20.11 | cross_modal_coincidence | committed | 5c4a5b32 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:20.00 | 00:30.00 | unknown | committed | 7f8859ca | В аудио не слышно речи человека. [uncertain; cosine=0.729; speech_absent] |
| 00:20.00 | 00:55.00 | unknown | committed | a4478639 | Музыка звучит на первом плане и преобладает в аудио. [uncertain; cosine=0.773; music_present] |
| 00:23.00 | 00:24.05 | cross_modal_coincidence | committed | a9d9ae3d | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:25.00 | 00:26.02 | cross_modal_coincidence | committed | 4c4f085b | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:29.21 | 00:44.21 | unknown | committed | 486d4e85 | На изображении виден читаемый текст. [uncertain; cosine=0.605; screen_text_visible] |
| 00:29.21 | 00:44.21 | unknown | committed | 72e182d4 | unknown [uncertain; cosine=0.584; unknown] |
| 00:32.00 | 00:33.05 | cross_modal_coincidence | committed | 01e4aec0 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:35.00 | 00:55.00 | unknown | committed | 230ef69f | В аудио не слышно речи человека. [uncertain; cosine=0.732; speech_absent] |
| 00:38.00 | 00:39.05 | cross_modal_coincidence | committed | a32e783f | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:39.00 | 00:40.08 | cross_modal_coincidence | committed | 0d053365 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:40.00 | 00:41.00 | cross_modal_coincidence | committed | 35a526da | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:41.00 | 00:42.00 | cross_modal_coincidence | committed | 80341bed | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:42.00 | 00:43.00 | cross_modal_coincidence | committed | b71a8d53 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:43.00 | 00:44.00 | cross_modal_coincidence | committed | e51bb38c | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:44.00 | 00:45.00 | cross_modal_coincidence | committed | a721e552 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:45.00 | 00:46.00 | cross_modal_coincidence | committed | 6285424c | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:46.00 | 00:47.00 | cross_modal_coincidence | committed | 613506cd | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:47.00 | 00:48.09 | cross_modal_coincidence | committed | 463fc085 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:48.00 | 00:49.02 | cross_modal_coincidence | committed | f3049689 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:51.00 | 00:52.00 | cross_modal_coincidence | committed | 1a936078 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:52.00 | 00:53.01 | cross_modal_coincidence | committed | f0d90a6b | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:54.00 | 00:55.00 | cross_modal_coincidence | committed | af66340a | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:55.00 | 00:56.01 | cross_modal_coincidence | committed | 435e831e | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:55.00 | 01:05.00 | unknown | committed | ed9deab5 | В аудио слышна речь человека. [uncertain; cosine=0.763; speech_present] |
| 00:56.00 | 00:57.09 | cross_modal_coincidence | committed | ea3f8efb | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:57.00 | 00:58.00 | cross_modal_coincidence | committed | 374e64e4 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:00.00 | 01:01.09 | cross_modal_coincidence | committed | 6a78f6d6 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:00.00 | 01:10.00 | unknown | committed | 540e5b0c | Музыка звучит на первом плане и преобладает в аудио. [uncertain; cosine=0.786; music_present] |
| 01:01.00 | 01:02.05 | cross_modal_coincidence | committed | ecdf3b1a | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:03.00 | 01:04.00 | cross_modal_coincidence | committed | 1d247aa8 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:09.00 | 01:10.00 | cross_modal_coincidence | committed | e6603282 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:10.00 | 01:25.00 | audio_scene_changed | committed | db7693c5 | На первом плане слышен разговор людей. [accepted; cosine=0.747; conversation_dominant] |
| 01:12.00 | 01:13.06 | cross_modal_coincidence | committed | 571cc00d | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:13.00 | 01:14.00 | cross_modal_coincidence | committed | 417dd91a | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:15.00 | 01:30.00 | unknown | committed | 33b2e14b | В аудио слышна речь человека. [uncertain; cosine=0.727; speech_present] |
| 01:16.00 | 01:17.00 | cross_modal_coincidence | committed | cb21db42 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:17.00 | 01:18.02 | cross_modal_coincidence | committed | 3f973885 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:18.00 | 01:19.05 | cross_modal_coincidence | committed | 5ec6be59 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:20.00 | 01:21.00 | cross_modal_coincidence | committed | 075c4251 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:21.00 | 01:22.02 | cross_modal_coincidence | committed | a8b5f402 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:23.00 | 01:24.06 | cross_modal_coincidence | committed | 32e9bf58 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:24.00 | 01:25.00 | cross_modal_coincidence | committed | 958c425c | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:25.00 | 01:26.00 | cross_modal_coincidence | committed | 5b220ef7 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:26.00 | 01:27.00 | cross_modal_coincidence | committed | dfdb3752 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:27.00 | 01:28.02 | cross_modal_coincidence | committed | e11e0579 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:28.00 | 01:29.00 | cross_modal_coincidence | committed | 3c188db5 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |

## L2 события

| Начало | Конец | Тип | Статус | ID | Русские claims (решение; cosine; label) |
|---:|---:|---|---|---|---|
| 00:00.00 | 00:10.00 | unknown | committed | 207caff0 | В аудио преобладают звуки окружающей среды и повседневные шумы. [uncertain; cosine=0.756; environment_dominant] |
| 00:00.00 | 00:10.00 | unknown | committed | 70b7558b | unknown [uncertain; cosine=0.583; unknown] |
| 00:00.00 | 00:10.00 | unknown | committed | 94f7612b | В аудио не слышно речи человека. [uncertain; cosine=0.729; speech_absent] |
| 00:00.00 | 00:10.00 | unknown | committed | fd465b80 | На изображении виден человек. [uncertain; cosine=0.622; person_visible] |
| 00:00.00 | 01:30.00 | unknown | committed | 075c1be3 | Слышен один или несколько коротких ударных звуков. [uncertain; cosine=0.750; impact_present] |
| 00:00.00 | 01:30.00 | unknown | committed | 937f1583 | Слышен непрерывный фоновый звук окружающей среды. [uncertain; cosine=0.758; ambient_sound_present] |
| 00:01.00 | 00:02.00 | scene_changed | refined | 5e92bb3b | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:01.00 | 00:02.00 | cross_modal_coincidence | committed | a1386ef0 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:02.00 | 00:03.00 | scene_changed | refined | 649a3c9c | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:02.00 | 00:03.00 | cross_modal_coincidence | committed | da2b587b | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:03.00 | 00:04.00 | scene_changed | refined | f3eebf69 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:03.00 | 00:04.01 | cross_modal_coincidence | committed | 54261b5e | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:04.00 | 00:05.00 | scene_changed | refined | 3e42200c | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:04.00 | 00:05.00 | cross_modal_coincidence | committed | d41f8d6f | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:05.00 | 00:06.00 | scene_changed | refined | 54cb4959 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:05.00 | 00:06.03 | cross_modal_coincidence | committed | 833c8cfe | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:06.00 | 00:07.00 | scene_changed | refined | 91ab0b14 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:06.00 | 00:07.01 | cross_modal_coincidence | committed | 266657be | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:07.00 | 00:08.00 | scene_changed | refined | 042b15ac | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:07.00 | 00:08.00 | cross_modal_coincidence | committed | 0d63901c | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:10.00 | 00:20.00 | unknown | committed | cc4cead6 | В аудио слышна речь человека. [uncertain; cosine=0.743; speech_present] |
| 00:14.00 | 00:15.00 | scene_changed | refined | c6bc5aac | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:14.00 | 00:15.05 | cross_modal_coincidence | committed | 69328a96 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:19.00 | 00:20.00 | scene_changed | refined | d5ab98c8 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:19.00 | 00:20.11 | cross_modal_coincidence | committed | 5c4a5b32 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:20.00 | 00:30.00 | unknown | committed | 7f8859ca | В аудио не слышно речи человека. [uncertain; cosine=0.729; speech_absent] |
| 00:20.00 | 00:55.00 | unknown | committed | a4478639 | Музыка звучит на первом плане и преобладает в аудио. [uncertain; cosine=0.773; music_present] |
| 00:23.00 | 00:24.00 | scene_changed | refined | a381a863 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:23.00 | 00:24.05 | cross_modal_coincidence | committed | a9d9ae3d | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:25.00 | 00:26.00 | scene_changed | refined | 2f99e535 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:25.00 | 00:26.02 | cross_modal_coincidence | committed | 4c4f085b | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:29.21 | 00:44.21 | unknown | committed | 486d4e85 | На изображении виден читаемый текст. [uncertain; cosine=0.605; screen_text_visible] |
| 00:29.21 | 00:44.21 | unknown | committed | 72e182d4 | unknown [uncertain; cosine=0.584; unknown] |
| 00:32.00 | 00:33.00 | scene_changed | refined | ea4bbe6a | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:32.00 | 00:33.05 | cross_modal_coincidence | committed | 01e4aec0 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:35.00 | 00:55.00 | unknown | committed | 230ef69f | В аудио не слышно речи человека. [uncertain; cosine=0.732; speech_absent] |
| 00:38.00 | 00:39.00 | scene_changed | refined | 07cfabfc | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:38.00 | 00:39.05 | cross_modal_coincidence | committed | a32e783f | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:39.00 | 00:40.00 | scene_changed | refined | 6566b7df | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:39.00 | 00:40.08 | cross_modal_coincidence | committed | 0d053365 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:40.00 | 00:41.00 | scene_changed | refined | 169e47c9 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:40.00 | 00:41.00 | cross_modal_coincidence | committed | 35a526da | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:41.00 | 00:42.00 | cross_modal_coincidence | committed | 80341bed | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:41.00 | 00:42.00 | scene_changed | refined | eb5e5062 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:42.00 | 00:43.00 | cross_modal_coincidence | committed | b71a8d53 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:42.00 | 00:43.00 | scene_changed | refined | dd8f653a | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:43.00 | 00:44.00 | scene_changed | refined | 5321cbc7 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:43.00 | 00:44.00 | cross_modal_coincidence | committed | e51bb38c | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:44.00 | 00:45.00 | scene_changed | refined | 13d49f7a | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:44.00 | 00:45.00 | cross_modal_coincidence | committed | a721e552 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:45.00 | 00:46.00 | scene_changed | refined | 47189d9b | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:45.00 | 00:46.00 | cross_modal_coincidence | committed | 6285424c | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:46.00 | 00:47.00 | scene_changed | refined | 491eb25c | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:46.00 | 00:47.00 | cross_modal_coincidence | committed | 613506cd | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:47.00 | 00:48.00 | scene_changed | refined | 287e85b6 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:47.00 | 00:48.09 | cross_modal_coincidence | committed | 463fc085 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:48.00 | 00:49.00 | scene_changed | refined | cfc2dc34 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:48.00 | 00:49.02 | cross_modal_coincidence | committed | f3049689 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:51.00 | 00:52.00 | cross_modal_coincidence | committed | 1a936078 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:51.00 | 00:52.00 | scene_changed | refined | 759d2617 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:52.00 | 00:53.00 | scene_changed | refined | c1770af9 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:52.00 | 00:53.01 | cross_modal_coincidence | committed | f0d90a6b | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:54.00 | 00:55.00 | cross_modal_coincidence | committed | af66340a | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:54.00 | 00:55.00 | scene_changed | refined | f546fc93 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:55.00 | 00:56.00 | scene_changed | refined | 1eb04fd8 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:55.00 | 00:56.01 | cross_modal_coincidence | committed | 435e831e | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:55.00 | 01:05.00 | unknown | committed | ed9deab5 | В аудио слышна речь человека. [uncertain; cosine=0.763; speech_present] |
| 00:56.00 | 00:57.00 | scene_changed | refined | 121437db | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 00:56.00 | 00:57.09 | cross_modal_coincidence | committed | ea3f8efb | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:57.00 | 00:58.00 | cross_modal_coincidence | committed | 374e64e4 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 00:57.00 | 00:58.00 | scene_changed | refined | 77a0f5b6 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:00.00 | 01:01.00 | scene_changed | refined | f7133940 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:00.00 | 01:01.09 | cross_modal_coincidence | committed | 6a78f6d6 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:00.00 | 01:10.00 | unknown | committed | 540e5b0c | Музыка звучит на первом плане и преобладает в аудио. [uncertain; cosine=0.786; music_present] |
| 01:01.00 | 01:02.00 | scene_changed | refined | 41b69ee9 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:01.00 | 01:02.05 | cross_modal_coincidence | committed | ecdf3b1a | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:03.00 | 01:04.00 | cross_modal_coincidence | committed | 1d247aa8 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:03.00 | 01:04.00 | scene_changed | refined | e06ce3ed | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:09.00 | 01:10.00 | scene_changed | refined | 03449e3c | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:09.00 | 01:10.00 | cross_modal_coincidence | committed | e6603282 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:10.00 | 01:25.00 | audio_scene_changed | refined | db7693c5 | На первом плане слышен разговор людей. [accepted; cosine=0.809; conversation_dominant]<br>В музыке отчётливо слышен ритм ударных. [accepted; cosine=0.737; percussion_present] |
| 01:12.00 | 01:13.00 | scene_changed | committed | 7f36e36d | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:12.00 | 01:13.06 | cross_modal_coincidence | committed | 571cc00d | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:13.00 | 01:14.00 | cross_modal_coincidence | committed | 417dd91a | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:13.00 | 01:14.00 | scene_changed | committed | 4e70c74e | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:15.00 | 01:30.00 | unknown | committed | 33b2e14b | В аудио слышна речь человека. [uncertain; cosine=0.727; speech_present] |
| 01:16.00 | 01:17.00 | scene_changed | committed | c58e214c | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:16.00 | 01:17.00 | cross_modal_coincidence | committed | cb21db42 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:17.00 | 01:18.00 | scene_changed | committed | 4f602da6 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:17.00 | 01:18.02 | cross_modal_coincidence | committed | 3f973885 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:18.00 | 01:19.00 | scene_changed | committed | b0eae402 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:18.00 | 01:19.05 | cross_modal_coincidence | committed | 5ec6be59 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:20.00 | 01:21.00 | cross_modal_coincidence | committed | 075c4251 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:20.00 | 01:21.00 | scene_changed | committed | ce34a714 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:21.00 | 01:22.00 | scene_changed | committed | eeba1e06 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:21.00 | 01:22.02 | cross_modal_coincidence | committed | a8b5f402 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:23.00 | 01:24.00 | scene_changed | committed | 15f93555 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:23.00 | 01:24.06 | cross_modal_coincidence | committed | 32e9bf58 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:24.00 | 01:25.00 | scene_changed | committed | 921ff63c | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:24.00 | 01:25.00 | cross_modal_coincidence | committed | 958c425c | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:25.00 | 01:26.00 | scene_changed | refined | 3717fab4 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:25.00 | 01:26.00 | cross_modal_coincidence | committed | 5b220ef7 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:26.00 | 01:27.00 | scene_changed | refined | 5934a687 | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:26.00 | 01:27.00 | cross_modal_coincidence | committed | dfdb3752 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:27.00 | 01:28.00 | scene_changed | refined | 5cffebba | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:27.00 | 01:28.02 | cross_modal_coincidence | committed | e11e0579 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |
| 01:28.00 | 01:29.00 | scene_changed | refined | 29ea9e7e | Обнаружено заметное изменение изображения. [accepted; scene_cut] |
| 01:28.00 | 01:29.00 | cross_modal_coincidence | committed | 3c188db5 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. [accepted; temporally_coincident] |

## L3 описания Qwen

| Интервал | Русское описание | Время генерации | Источники |
|---|---|---:|---|
| 00:01.00–00:03.00 | Обнаружено заметное изменение изображения. | 3347 мс | 5e92bb3b, a1386ef0, 649a3c9c |
| 01:10.00–01:25.00 | На первом плане слышен разговор людей. | 4531 мс | db7693c5, 7f36e36d |
| 01:28.00–01:29.00 | Смена кадра совпадает по времени с обнаруженным звуковым началом. | 2686 мс | 3c188db5 |

## Ограничения оценки

- В этом репозитории нет независимых ручных музыкальных меток для этих интервалов. Поэтому повышение cosine/числа подтверждений не доказывает точность и отсутствие FP.
- Cosine similarity — оценка сходства текста и эмбеддинга, а не вероятность.
- Qwen и L2 здесь запускались после чтения локального файла; задержки не описывают непрерывную live обработку.
- Веса моделей не изменялись.

## Тайминги стадий офлайн прогона

Эти значения суммарные; стадии частично перекрываются и их нельзя складывать в задержку одного события.

- `audio_consumer_work`: 897.3 мс.
- `embedding_inference`: 22600.2 мс.
- `embedding_model_and_text_profiles`: 12463.6 мс.
- `embedding_result_apply`: 49.1 мс.
- `embedding_worker_elapsed`: 22785.9 мс.
- `l1_match_and_reduce`: 663.6 мс.
- `l2_state_refinement`: 383.7 мс.
- `l3_narration`: 11211.4 мс.
- `shared_media_interleave`: 30987.2 мс.
- `video_consumer_work`: 22090.2 мс.
