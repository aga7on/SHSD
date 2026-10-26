# Real-video L1/L2/L3 output

## Run

- Source: X:\AI\SHSD\benchmarks\fixtures\real_poc\tears_of_steel_120_210s.mp4
- Duration: 90000 ms; CPU; 4 threads; 5000 ms windows; Qwen narrator.
- End-to-end elapsed: 93.711274 s. File-mode L2/L3 were produced after media collection completed.
- Event revisions in JSONL: 220; window matches: 92; skipped matches: 108.
- Event record counts across revisions: L0=46, L1=112, L2=62; latest L1/L2 rows are listed below (121 rows).

## Semantic matcher scores

Cosines are scores, not probabilities. The required policy is read from each raw match; see semantic_match_scores.csv for every candidate ranking.

| Axis | Modality | Windows | Decisions | Best cosine min/mean/max | Top-two gap min/mean/max |
|---|---|---:|---|---|---|
| ambient_sound | audio | 18 | {'uncertain': 18} | 0.678/0.758/0.812 | 0.002/0.019/0.043 |
| impact_sound | audio | 18 | {'uncertain': 18} | 0.699/0.750/0.788 | 0.001/0.018/0.045 |
| music_presence | audio | 18 | {'uncertain': 18} | 0.673/0.736/0.775 | 0.000/0.010/0.018 |
| person_presence | image | 5 | {'uncertain': 5} | 0.617/0.626/0.640 | 0.019/0.029/0.043 |
| scene_setting | image | 5 | {'uncertain': 5} | 0.614/0.623/0.641 | 0.004/0.013/0.039 |
| scene_style | image | 5 | {'uncertain': 5} | 0.572/0.584/0.594 | 0.000/0.000/0.000 |
| screen_text_presence | image | 5 | {'uncertain': 5} | 0.591/0.608/0.620 | 0.005/0.012/0.024 |
| speech_presence | audio | 18 | {'uncertain': 17, 'accepted': 1} | 0.714/0.737/0.770 | 0.002/0.014/0.058 |

## L1 and L2 events

Descriptions below are the model's Russian claim text. The decision is kept beside each description; uncertain claims are not treated as verified facts.

| Source range | Level | State | Kind | Russian claim descriptions | Event/revision |
|---|---|---|---|---|---|
| 0-10000 ms | L1 | committed | unknown | speech_absent [uncertain]: В аудио не слышно речи человека. | 056d93c9b295454f9d1a2987aadee43a r2 |
| 0-90000 ms | L1 | committed | unknown | ambient_sound_present [uncertain]: Слышен непрерывный фоновый звук окружающей среды. | 1b87782a3d8b4941a835af1d0b1ce18a r18 |
| 0-90000 ms | L1 | committed | unknown | impact_present [uncertain]: Слышен один или несколько коротких ударных звуков. | 7c2c546f7ef04247b4f3e24aea326067 r18 |
| 0-10000 ms | L1 | committed | unknown | music_absent [uncertain]: В аудио не слышно музыки. | 99292a533e6c4062a9a3ac92ca882f62 r2 |
| 0-10000 ms | L2 | committed | unknown | speech_absent [uncertain]: В аудио не слышно речи человека. | 056d93c9b295454f9d1a2987aadee43a r3 |
| 0-90000 ms | L2 | committed | unknown | ambient_sound_present [uncertain]: Слышен непрерывный фоновый звук окружающей среды. | 1b87782a3d8b4941a835af1d0b1ce18a r19 |
| 0-90000 ms | L2 | committed | unknown | impact_present [uncertain]: Слышен один или несколько коротких ударных звуков. | 7c2c546f7ef04247b4f3e24aea326067 r19 |
| 0-10000 ms | L2 | committed | unknown | music_absent [uncertain]: В аудио не слышно музыки. | 99292a533e6c4062a9a3ac92ca882f62 r3 |
| 1000-2000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | e3bba5ac7a7541b2a550a682fe5ed252 r1 |
| 1000-2000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 43b4da62365e43d78bb114c86b5693c6 r2 |
| 1000-2000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | e3bba5ac7a7541b2a550a682fe5ed252 r2 |
| 2000-3000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | ba7b92ce3a684f329642ad26d15aa1f7 r1 |
| 2000-3000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | ba7b92ce3a684f329642ad26d15aa1f7 r2 |
| 2000-3000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | c6528abe3e5a4c62ba7a6d3d55a6d2b3 r2 |
| 3000-4015 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 82d905f31f764073b7d4f9bb61628567 r1 |
| 3000-4015 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 82d905f31f764073b7d4f9bb61628567 r2 |
| 3000-4000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | a7d9c91e1f1c4771abca4c683bfe9e85 r2 |
| 4000-5000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 9a16c6c8c931432bbdebbb8418f4567b r1 |
| 4000-5000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 962b98e761604169a9dc2b80504e9594 r2 |
| 4000-5000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 9a16c6c8c931432bbdebbb8418f4567b r2 |
| 5000-6025 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 15e8a2ed47fd498792312739104e3f62 r1 |
| 5000-6025 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 15e8a2ed47fd498792312739104e3f62 r2 |
| 5000-6000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | b5e5c11fec034ac1b11b9e5a200e9ac5 r2 |
| 6000-7015 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 09f180090a784f28b7cdcb01e3e7bcbd r1 |
| 6000-7000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 03f8c7d56a094dd488eeb8c437285617 r2 |
| 6000-7015 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 09f180090a784f28b7cdcb01e3e7bcbd r2 |
| 7000-8000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 93b78e1ce3934a93bbef4279ba19cdd9 r1 |
| 7000-8000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 08cb7485572542abbed29a77d5fc823e r2 |
| 7000-8000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 93b78e1ce3934a93bbef4279ba19cdd9 r2 |
| 10000-20000 ms | L1 | committed | unknown | speech_present [uncertain]: В аудио слышна речь человека. | 18b5443446e848719195dccf174af16c r2 |
| 10000-20000 ms | L2 | committed | unknown | speech_present [uncertain]: В аудио слышна речь человека. | 18b5443446e848719195dccf174af16c r3 |
| 14000-15055 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 75a4e978d7c2404fbb81f853424d19f3 r1 |
| 14000-15055 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 75a4e978d7c2404fbb81f853424d19f3 r2 |
| 14000-15000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | d046ce1423f64786bb12977ca46fb768 r2 |
| 15000-30000 ms | L1 | committed | unknown | music_absent [uncertain]: В аудио не слышно музыки. | 94e82f8ecdf549cbbe9fdb06f1372bcb r3 |
| 15000-30000 ms | L2 | committed | unknown | music_absent [uncertain]: В аудио не слышно музыки. | 94e82f8ecdf549cbbe9fdb06f1372bcb r4 |
| 19000-20105 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 79b5986840ef489792aa026e720e8d52 r1 |
| 19000-20000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 0f4e4d78a00b4e2da2ac789bed71adc8 r2 |
| 19000-20105 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 79b5986840ef489792aa026e720e8d52 r2 |
| 20000-30000 ms | L1 | committed | unknown | speech_absent [uncertain]: В аудио не слышно речи человека. | 15451514506f44348eac5cdce5b1d9af r2 |
| 20000-30000 ms | L2 | committed | unknown | speech_absent [uncertain]: В аудио не слышно речи человека. | 15451514506f44348eac5cdce5b1d9af r3 |
| 23000-24045 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | e920e6e650de4d19a17559e841df27a3 r1 |
| 23000-24000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 606243dc098d4c73b99b85caf51b130d r2 |
| 23000-24045 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | e920e6e650de4d19a17559e841df27a3 r2 |
| 25000-26025 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | d0304f3bfc564e3284afd6f0f13b3df3 r1 |
| 25000-26000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 3ff1e952ad4a435f95cc5f66fcc78da0 r2 |
| 25000-26025 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | d0304f3bfc564e3284afd6f0f13b3df3 r2 |
| 30000-40000 ms | L1 | committed | unknown | music_present [uncertain]: В аудио слышна музыка. | 3257954d92e844ecbeeb2cd474280e2c r2 |
| 30000-40000 ms | L2 | committed | unknown | music_present [uncertain]: В аудио слышна музыка. | 3257954d92e844ecbeeb2cd474280e2c r3 |
| 32000-33055 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 0eb938217f6346b499dea0e821abd851 r1 |
| 32000-33055 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 0eb938217f6346b499dea0e821abd851 r2 |
| 32000-33000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 4d4bb3155be34da9a0be92efe5e905bf r2 |
| 35000-55000 ms | L1 | committed | unknown | speech_absent [uncertain]: В аудио не слышно речи человека. | 48024b3db36a40688f3b1fc010334d74 r4 |
| 35000-55000 ms | L2 | committed | unknown | speech_absent [uncertain]: В аудио не слышно речи человека. | 48024b3db36a40688f3b1fc010334d74 r5 |
| 38000-39055 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 98326f29d71244a29ac977318514e639 r1 |
| 38000-39055 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 98326f29d71244a29ac977318514e639 r2 |
| 38000-39000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | d861c39dcc3d41ae9c5157b6eae328e8 r2 |
| 39000-40075 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 337379197f114a67b099624d51ba2fd0 r1 |
| 39000-40075 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 337379197f114a67b099624d51ba2fd0 r2 |
| 39000-40000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 62e3ebd964ab4098a0ffb2f023b617f0 r2 |
| 40000-60000 ms | L1 | committed | unknown | music_absent [uncertain]: В аудио не слышно музыки. | 0b3d50917e3048f8baff6b0a5d20f548 r4 |
| 40000-41000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | db720269f6c24bf0ad1a297121b68005 r1 |
| 40000-60000 ms | L2 | committed | unknown | music_absent [uncertain]: В аудио не слышно музыки. | 0b3d50917e3048f8baff6b0a5d20f548 r5 |
| 40000-41000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 462849a8702e42d0bd311162e43f7fad r2 |
| 40000-41000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | db720269f6c24bf0ad1a297121b68005 r2 |
| 41000-42000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 92d80bb34f2d4d7b8b3d65c1ae5a3c15 r1 |
| 41000-42000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 58bc73a70d404be99c0849381fa6ddde r2 |
| 41000-42000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 92d80bb34f2d4d7b8b3d65c1ae5a3c15 r2 |
| 42000-43000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 149aabfea9d142478e89794addecfc3e r1 |
| 42000-43000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 149aabfea9d142478e89794addecfc3e r2 |
| 42000-43000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | dc83472c050d4787bd03f9bc617f060f r2 |
| 43000-44000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 3c852d8bdbd745aab5bb00ca0863b9e6 r1 |
| 43000-44000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 3c852d8bdbd745aab5bb00ca0863b9e6 r2 |
| 43000-44000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 6c05381635f546548d14be74dcc8ad22 r2 |
| 44000-45000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 4200dfd6dd2f4dabb5dd3c017dcef839 r1 |
| 44000-45000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 4200dfd6dd2f4dabb5dd3c017dcef839 r2 |
| 44000-45000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 570f370542f24956b170eaa9f1910eed r2 |
| 45000-46000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 4a48911c5c834fab9b5f99ee2ca4a95b r1 |
| 45000-46000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 0d30d0e38d3a45b0972e21606d7a10e9 r2 |
| 45000-46000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 4a48911c5c834fab9b5f99ee2ca4a95b r2 |
| 46000-47000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 12fbc1ad4aff4ccbb895087eed36628d r1 |
| 46000-47000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 12fbc1ad4aff4ccbb895087eed36628d r2 |
| 46000-47000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | ca664b2601b2462b9659a3e5e1e43e03 r2 |
| 47000-48095 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 66796bee7cb048769686d9e40867a7a1 r1 |
| 47000-48095 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 66796bee7cb048769686d9e40867a7a1 r2 |
| 47000-48000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 6cc9cbe0202141d5b6e080482d56a8fa r2 |
| 48000-49015 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | eea708e776d64bca9e5cee3cfd40ab96 r1 |
| 48000-49000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 6d4375eaf1434e2e92a59c668a617187 r2 |
| 48000-49015 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | eea708e776d64bca9e5cee3cfd40ab96 r2 |
| 51000-52000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 78d73e1be619484dafe750e3a8aad72b r1 |
| 51000-52000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 78d73e1be619484dafe750e3a8aad72b r2 |
| 51000-52000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 8503b83ca4b14634969b6b5205f292a2 r2 |
| 52000-53005 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 69b1768ed9804fa6942ae88154f6f4d2 r1 |
| 52000-53000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 23d6a63bb09541648a23a60b47021453 r2 |
| 52000-53005 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 69b1768ed9804fa6942ae88154f6f4d2 r2 |
| 54000-55000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | a889fd94d5b54cd7b95d5504b4e1998c r1 |
| 54000-55000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 039ef7075be74cc9b348cf38952dc018 r2 |
| 54000-55000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | a889fd94d5b54cd7b95d5504b4e1998c r2 |
| 55000-56005 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 3a95d88d5f4a41879fd0dce929eff22f r1 |
| 55000-65000 ms | L1 | committed | unknown | speech_present [uncertain]: В аудио слышна речь человека. | b6b90ad7e9464311806c6982a8084c1f r2 |
| 56000-57085 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 83ea9a2916a34bfbbee596eff0ed6774 r1 |
| 57000-58000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 1f60f960fb8e450ca8a4bcc01a18c77d r1 |
| 60000-61085 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 2bc9b679e6934b5f994c6e107cada481 r1 |
| 61000-62055 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | c08cf5d83aa74a86adafa4b694bc4a5d r1 |
| 63000-64000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | d0ed2aeb5ce846ad88fca3be07293ffa r1 |
| 69000-70000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | ed40b8f972ad4a54abdea6101c09d02c r1 |
| 70000-90000 ms | L1 | committed | unknown | music_present [uncertain]: В аудио слышна музыка. | d002ba4030e94cb9b80ddfe88b2b48f9 r4 |
| 72000-73055 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 3b1646ddcd06445b9e90b5fd1543df13 r1 |
| 73000-74000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 2aac40e5e937446a859724fe085c37b4 r1 |
| 75000-90000 ms | L1 | committed | unknown | speech_present [uncertain]: В аудио слышна речь человека. | 240d7a11558b4f2a934549efe9faa417 r3 |
| 76000-77000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | e3562b105a5e4256b8a45ade1e257ff9 r1 |
| 77000-78015 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | d76ced527dda4feb95e1d5911f814d66 r1 |
| 78000-79045 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | c7a0cd4df1244d36bda9fed259b8d571 r1 |
| 80000-81000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | cff85c8abd8342068ada4cee32f32bc7 r1 |
| 81000-82015 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 22da0f9d682342fbbdfedc600c1ef1e0 r1 |
| 83000-84065 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | e636aeb3117d4cdc945bac2a67c3fdef r1 |
| 84000-85000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 2b69ff5cf7184be0a4bde2742a404e2b r1 |
| 85000-86000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 172276c73cd041a89988dec9f1559215 r1 |
| 86000-87000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 2e50a5823285493d890b9512424cd75e r1 |
| 87000-88015 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | ad057eec8d534c01b2a1166074d5fbb5 r1 |
| 88000-89000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 40ff64b54a3f43ab90d8ee25b2ec3cfa r1 |

## L3 captions

Qwen status counts: {('generated', 'qwen'): 8, ('fallback', 'qwen'): 10}. Most common caption (8 occurrences): Обнаружено заметное изменение изображения.

| Source range | Status | Russian caption | Cited event revisions |
|---|---|---|---|
| 1000-4000 ms | generated | Обнаружено заметное изменение изображения. | 43b4da62365e43d78bb114c86b5693c6 r2, c6528abe3e5a4c62ba7a6d3d55a6d2b3 r2, a7d9c91e1f1c4771abca4c683bfe9e85 r2 |
| 4000-7000 ms | generated | Обнаружено заметное изменение изображения. | 962b98e761604169a9dc2b80504e9594 r2, b5e5c11fec034ac1b11b9e5a200e9ac5 r2, 03f8c7d56a094dd488eeb8c437285617 r2 |
| 7000-20000 ms | generated | Обнаружено заметное изменение изображения. | 08cb7485572542abbed29a77d5fc823e r2, d046ce1423f64786bb12977ca46fb768 r2, 0f4e4d78a00b4e2da2ac789bed71adc8 r2 |
| 23000-33000 ms | generated | Обнаружено заметное изменение изображения. | 606243dc098d4c73b99b85caf51b130d r2, 3ff1e952ad4a435f95cc5f66fcc78da0 r2, 4d4bb3155be34da9a0be92efe5e905bf r2 |
| 38000-41000 ms | generated | Обнаружено заметное изменение изображения. | d861c39dcc3d41ae9c5157b6eae328e8 r2, 62e3ebd964ab4098a0ffb2f023b617f0 r2, 462849a8702e42d0bd311162e43f7fad r2 |
| 41000-44000 ms | generated | Обнаружено заметное изменение изображения. | 58bc73a70d404be99c0849381fa6ddde r2, dc83472c050d4787bd03f9bc617f060f r2, 6c05381635f546548d14be74dcc8ad22 r2 |
| 44000-47000 ms | generated | Обнаружено заметное изменение изображения. | 570f370542f24956b170eaa9f1910eed r2, 0d30d0e38d3a45b0972e21606d7a10e9 r2, ca664b2601b2462b9659a3e5e1e43e03 r2 |
| 47000-52000 ms | generated | Обнаружено заметное изменение изображения. | 6cc9cbe0202141d5b6e080482d56a8fa r2, 6d4375eaf1434e2e92a59c668a617187 r2, 8503b83ca4b14634969b6b5205f292a2 r2 |
| 1000-55000 ms | fallback | Обнаружено заметное изменение изображения. Обнаружено заметное изменение изображения. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 23d6a63bb09541648a23a60b47021453 r2, 039ef7075be74cc9b348cf38952dc018 r2, e3bba5ac7a7541b2a550a682fe5ed252 r2 |
| 2000-5000 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | ba7b92ce3a684f329642ad26d15aa1f7 r2, 82d905f31f764073b7d4f9bb61628567 r2, 9a16c6c8c931432bbdebbb8418f4567b r2 |
| 5000-8000 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 15e8a2ed47fd498792312739104e3f62 r2, 09f180090a784f28b7cdcb01e3e7bcbd r2, 93b78e1ce3934a93bbef4279ba19cdd9 r2 |
| 14000-24045 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 75a4e978d7c2404fbb81f853424d19f3 r2, 79b5986840ef489792aa026e720e8d52 r2, e920e6e650de4d19a17559e841df27a3 r2 |
| 25000-39055 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | d0304f3bfc564e3284afd6f0f13b3df3 r2, 0eb938217f6346b499dea0e821abd851 r2, 98326f29d71244a29ac977318514e639 r2 |
| 39000-42000 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 337379197f114a67b099624d51ba2fd0 r2, db720269f6c24bf0ad1a297121b68005 r2, 92d80bb34f2d4d7b8b3d65c1ae5a3c15 r2 |
| 42000-45000 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 149aabfea9d142478e89794addecfc3e r2, 3c852d8bdbd745aab5bb00ca0863b9e6 r2, 4200dfd6dd2f4dabb5dd3c017dcef839 r2 |
| 45000-48095 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 4a48911c5c834fab9b5f99ee2ca4a95b r2, 12fbc1ad4aff4ccbb895087eed36628d r2, 66796bee7cb048769686d9e40867a7a1 r2 |
| 48000-53005 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | eea708e776d64bca9e5cee3cfd40ab96 r2, 78d73e1be619484dafe750e3a8aad72b r2, 69b1768ed9804fa6942ae88154f6f4d2 r2 |
| 54000-55000 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | a889fd94d5b54cd7b95d5504b4e1998c r2 |

## ASR and coverage

Speech segments: 5; dropped: 5; recognized transcript text was not emitted for dropped segments.

| Source range | Status | Text | Error |
|---|---|---|---|
| 40000-60000 ms | dropped |  | load_critical |
| 60000-80000 ms | dropped |  | load_critical |
| 80000-90000 ms | dropped |  | load_critical |
| 0-20000 ms | dropped |  | load_critical |
| 20000-40000 ms | dropped |  | load_critical |

Final watermarks: {"C": 90000, "D": {"L1": 90000, "L2": 90000, "L3": 90000}, "E": 90000, "R": {"L1": 90000, "L2": 90000, "L3": 90000}, "epoch": 0, "issues": [{"end_ms": 90000, "level": null, "modality": "speech", "reason": "load_critical", "revision": 1, "stage": "E", "start_ms": 0, "status": "dropped"}, {"end_ms": 20000, "level": null, "modality": "video", "reason": "runtime_backpressure", "revision": 1, "stage": "E", "start_ms": 1, "status": "skipped"}, {"end_ms": 40000, "level": null, "modality": "video", "reason": "embedding_stride", "revision": 1, "stage": "E", "start_ms": 20001, "status": "skipped"}, {"end_ms": 60000, "level": null, "modality": "video", "reason": "embedding_stride", "revision": 1, "stage": "E", "start_ms": 40001, "status": "skipped"}, {"end_ms": 80000, "level": null, "modality": "video", "reason": "embedding_stride", "revision": 1, "stage": "E", "start_ms": 60001, "status": "skipped"}, {"end_ms": 90000, "level": null, "modality": "video", "reason": "embedding_stride", "revision": 1, "stage": "E", "start_ms": 80001, "status": "skipped"}, {"end_ms": 90000, "level": "L2", "modality": null, "reason": "runtime_backpressure", "revision": 1, "stage": "D", "start_ms": 0, "status": "skipped"}, {"end_ms": 90000, "level": "L2", "modality": null, "reason": "runtime_backpressure", "revision": 1, "stage": "R", "start_ms": 0, "status": "skipped"}, {"end_ms": 1000, "level": "L3", "modality": null, "reason": "no_supported_claim_in_interval", "revision": 1, "stage": "R", "start_ms": 0, "status": "skipped"}, {"end_ms": 90000, "level": "L3", "modality": null, "reason": "no_supported_claim_in_interval", "revision": 1, "stage": "R", "start_ms": 55000, "status": "skipped"}], "lag_ms": {"L1": 0, "L2": 0, "L3": 0}, "modality_cursors": {"audio": {"C": 90000, "E": 90000}, "speech": {"C": 90000, "E": 90000}, "video": {"C": 90000, "E": 90000}}, "stream_id": "real-video-quality-20261026"}

Coverage issues:

- stage=D, level=L2, modality=-, reason=runtime_backpressure: 1 range(s)
- stage=E, level=-, modality=speech, reason=load_critical: 1 range(s)
- stage=E, level=-, modality=video, reason=embedding_stride: 4 range(s)
- stage=E, level=-, modality=video, reason=runtime_backpressure: 1 range(s)
- stage=R, level=L2, modality=-, reason=runtime_backpressure: 1 range(s)
- stage=R, level=L3, modality=-, reason=no_supported_claim_in_interval: 2 range(s)

## Reading the result

The run produces Russian event and caption strings, but the captions are repetitive scene-change descriptions and do not describe dialogue, music development, or instruments. The ASR worker dropped its windows under load_critical; uncertain L1 claims remain visible. This is a quality and coverage failure on this clip, not a positive accuracy result.

Machine-readable files: timeline.jsonl, semantic_match_scores.csv, events_l1_l2_latest.csv, captions_l3.csv, speech_segments.csv.
