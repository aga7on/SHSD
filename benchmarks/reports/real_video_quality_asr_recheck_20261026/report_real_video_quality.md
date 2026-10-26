# Real-video L1/L2/L3 output

## Run

- Source: X:\AI\SHSD\benchmarks\fixtures\real_poc\tears_of_steel_120_210s.mp4
- Duration: 90000 ms; CPU; 4 threads; 5000 ms windows; Qwen narrator.
- End-to-end elapsed: 87.625514 s. File-mode L2/L3 were produced after media collection completed.
- Event revisions in JSONL: 224; window matches: 96; skipped matches: 108.
- Event record counts across revisions: L0=46, L1=116, L2=62; latest L1/L2 rows are listed below (123 rows).

## Semantic matcher scores

Cosines are scores, not probabilities. The table counts rows below the per-match similarity and margin thresholds; margin basis distinguishes top-candidate gap from distance above the similarity threshold. The CSV includes each row's exact policy and candidate ranking.

| Axis | Modality | Windows | Decisions | Best cosine min/mean/max | Margin basis | Cosine below threshold | Margin below threshold | Margin min/mean/max |
|---|---|---:|---|---|---|---:|---:|---|
| ambient_sound | audio | 18 | {'uncertain': 18} | 0.678/0.758/0.812 | top_candidate_gap | 0 | 18 | 0.002/0.019/0.043 |
| impact_sound | audio | 18 | {'uncertain': 18} | 0.699/0.750/0.788 | top_candidate_gap | 0 | 18 | 0.001/0.018/0.045 |
| music_presence | audio | 18 | {'uncertain': 18} | 0.673/0.736/0.775 | top_candidate_gap | 0 | 18 | 0.000/0.010/0.018 |
| person_presence | image | 6 | {'uncertain': 6} | 0.614/0.624/0.641 | top_candidate_gap | 0 | 6 | 0.014/0.028/0.034 |
| scene_setting | image | 6 | {'uncertain': 6} | 0.632/0.639/0.651 | top_candidate_gap | 0 | 6 | 0.001/0.010/0.041 |
| scene_style | image | 6 | {'uncertain': 6} | 0.569/0.588/0.606 | similarity_threshold | 4 | 6 | 0.000/0.002/0.006 |
| screen_text_presence | image | 6 | {'uncertain': 6} | 0.593/0.601/0.621 | top_candidate_gap | 3 | 6 | 0.000/0.006/0.015 |
| speech_presence | audio | 18 | {'uncertain': 17, 'accepted': 1} | 0.714/0.737/0.770 | top_candidate_gap | 0 | 17 | 0.002/0.014/0.058 |

## L1 and L2 events

Descriptions below are the model's Russian claim text. The decision is kept beside each description; uncertain claims are not treated as verified facts.

| Source range | Level | State | Kind | Russian claim descriptions | Event/revision |
|---|---|---|---|---|---|
| 0-10000 ms | L1 | committed | unknown | speech_absent [uncertain]: В аудио не слышно речи человека. | 2db57328183e455aa5808fda4c6d855e r2 |
| 0-90000 ms | L1 | committed | unknown | impact_present [uncertain]: Слышен один или несколько коротких ударных звуков. | 5f04c5c9a33d4a51a43ad59aa5686f42 r18 |
| 0-90000 ms | L1 | committed | unknown | ambient_sound_present [uncertain]: Слышен непрерывный фоновый звук окружающей среды. | 6ff199f0a9854cb7965d6c43a1f97d8c r18 |
| 0-10000 ms | L1 | committed | unknown | unknown [uncertain] | 8a134b0832094f239f24170c85ac3ac1 r2 |
| 0-10000 ms | L1 | committed | unknown | person_visible [uncertain]: На изображении виден человек. | e6b8f71e63f64a11b63e146d712b0a37 r2 |
| 0-10000 ms | L1 | committed | unknown | music_absent [uncertain]: В аудио не слышно музыки. | ef6bdf8c179841869a719a1ad0f5d1d9 r2 |
| 0-10000 ms | L2 | committed | unknown | speech_absent [uncertain]: В аудио не слышно речи человека. | 2db57328183e455aa5808fda4c6d855e r3 |
| 0-90000 ms | L2 | committed | unknown | impact_present [uncertain]: Слышен один или несколько коротких ударных звуков. | 5f04c5c9a33d4a51a43ad59aa5686f42 r19 |
| 0-90000 ms | L2 | committed | unknown | ambient_sound_present [uncertain]: Слышен непрерывный фоновый звук окружающей среды. | 6ff199f0a9854cb7965d6c43a1f97d8c r19 |
| 0-10000 ms | L2 | committed | unknown | unknown [uncertain] | 8a134b0832094f239f24170c85ac3ac1 r3 |
| 0-10000 ms | L2 | committed | unknown | person_visible [uncertain]: На изображении виден человек. | e6b8f71e63f64a11b63e146d712b0a37 r3 |
| 0-10000 ms | L2 | committed | unknown | music_absent [uncertain]: В аудио не слышно музыки. | ef6bdf8c179841869a719a1ad0f5d1d9 r3 |
| 1000-2000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 3183aff5850943419478cb8eed8df589 r1 |
| 1000-2000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 3183aff5850943419478cb8eed8df589 r2 |
| 1000-2000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | f2d8091ff7504a7db7897e7abb003a10 r2 |
| 2000-3000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | f9cf8d47010a4e20b0fb6ca1c87f174c r1 |
| 2000-3000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 6bcd14d01523460690aa1df0ead517ac r2 |
| 2000-3000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | f9cf8d47010a4e20b0fb6ca1c87f174c r2 |
| 3000-4015 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | d819a1b1ef444ab09c8f218b3acebca2 r1 |
| 3000-4000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 67ba00aeb6e245129f217169dd467c47 r2 |
| 3000-4015 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | d819a1b1ef444ab09c8f218b3acebca2 r2 |
| 4000-5000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 1d01c12ef21f4cabbcc30a7993bbb9ec r1 |
| 4000-5000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 1d01c12ef21f4cabbcc30a7993bbb9ec r2 |
| 4000-5000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 775cc8cbe6aa451c8391a3336e80dbe2 r2 |
| 5000-6025 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 4760cb4ec8fd4181a7e64d68c7ebfe31 r1 |
| 5000-6025 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 4760cb4ec8fd4181a7e64d68c7ebfe31 r2 |
| 5000-6000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 9f3b60ddf8d149d4a5a013388fab83b4 r2 |
| 6000-7015 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 3370bfc2a9b24f5aa5458a01f8eb78f2 r1 |
| 6000-7015 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 3370bfc2a9b24f5aa5458a01f8eb78f2 r2 |
| 6000-7000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 6b78506abc0b4635acbbcac9dc56d23c r2 |
| 7000-8000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 28afcdca479f4fecbd0abdec13646006 r1 |
| 7000-8000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 28afcdca479f4fecbd0abdec13646006 r2 |
| 7000-8000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 4dac8b7b13d54d61897d543d7e9e33b7 r2 |
| 10000-20000 ms | L1 | committed | unknown | speech_present [uncertain]: В аудио слышна речь человека. | 5c58216807a943f38f10941907a325f0 r2 |
| 10000-20000 ms | L2 | committed | unknown | speech_present [uncertain]: В аудио слышна речь человека. | 5c58216807a943f38f10941907a325f0 r3 |
| 14000-15055 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | bb75e2f4ea4d4d4d94171efcb38e9297 r1 |
| 14000-15000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 41b0bf430be942b48caa3d75259fd734 r2 |
| 14000-15055 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | bb75e2f4ea4d4d4d94171efcb38e9297 r2 |
| 15000-30000 ms | L1 | committed | unknown | music_absent [uncertain]: В аудио не слышно музыки. | 2283d380746c4996830b73e2b8cb408b r3 |
| 15000-30000 ms | L2 | committed | unknown | music_absent [uncertain]: В аудио не слышно музыки. | 2283d380746c4996830b73e2b8cb408b r4 |
| 19000-20105 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 6468ad1d729e4c9281478f8ba315ae8c r1 |
| 19000-20000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 3f0a07540d27408484e7b57e5d4e04ee r2 |
| 19000-20105 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 6468ad1d729e4c9281478f8ba315ae8c r2 |
| 20000-30000 ms | L1 | committed | unknown | speech_absent [uncertain]: В аудио не слышно речи человека. | 49a79db75b4c4570878211eef012a613 r2 |
| 20000-30000 ms | L2 | committed | unknown | speech_absent [uncertain]: В аудио не слышно речи человека. | 49a79db75b4c4570878211eef012a613 r3 |
| 23000-24045 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 2daf29f9e5224e4ba0a478768045e732 r1 |
| 23000-24045 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 2daf29f9e5224e4ba0a478768045e732 r2 |
| 23000-24000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 7914c301631f4a1ebbe6cbefd47ddf78 r2 |
| 25000-26025 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 504a647dc9a2493aba31b08e4aebda90 r1 |
| 25000-26025 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 504a647dc9a2493aba31b08e4aebda90 r2 |
| 25000-26000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | a5911d6f5e564c90be7c9ca126810883 r2 |
| 30000-40000 ms | L1 | committed | unknown | music_present [uncertain]: В аудио слышна музыка. | 2d6a485e50bd477399671ed8c862ec43 r2 |
| 30000-40000 ms | L2 | committed | unknown | music_present [uncertain]: В аудио слышна музыка. | 2d6a485e50bd477399671ed8c862ec43 r3 |
| 32000-33055 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | cb01a67fd21e4d509fa8b9476502f01a r1 |
| 32000-33000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | b22aa50622124ec883024a659801c10c r2 |
| 32000-33055 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | cb01a67fd21e4d509fa8b9476502f01a r2 |
| 35000-55000 ms | L1 | committed | unknown | speech_absent [uncertain]: В аудио не слышно речи человека. | b06ef5c71a0144b793860b23cfc72997 r4 |
| 35000-55000 ms | L2 | committed | unknown | speech_absent [uncertain]: В аудио не слышно речи человека. | b06ef5c71a0144b793860b23cfc72997 r5 |
| 38000-39055 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 8a5ca9e02f554a32b291e10674d4eee2 r1 |
| 38000-39000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 206292072df64a43be183071e05b34ca r2 |
| 38000-39055 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 8a5ca9e02f554a32b291e10674d4eee2 r2 |
| 39000-40075 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 6c0d574ef0bf48c5b6f5b32c56766834 r1 |
| 39000-40000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 1968eca49fd8470996793b9e218d3123 r2 |
| 39000-40075 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 6c0d574ef0bf48c5b6f5b32c56766834 r2 |
| 40000-41000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | c24928ab47aa4bae8f0dcd3b2df17bbb r1 |
| 40000-60000 ms | L1 | committed | unknown | music_absent [uncertain]: В аудио не слышно музыки. | dea0692f700f429abccae6481236ee82 r4 |
| 40000-41000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | c24928ab47aa4bae8f0dcd3b2df17bbb r2 |
| 40000-41000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | dc8fd397ce83446da57863d3d805fb50 r2 |
| 40000-60000 ms | L2 | committed | unknown | music_absent [uncertain]: В аудио не слышно музыки. | dea0692f700f429abccae6481236ee82 r5 |
| 41000-42000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | e37f172d8cb94f80bedfddc472a3c027 r1 |
| 41000-42000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 31328796b0f640bda9c954503ddd0622 r2 |
| 41000-42000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | e37f172d8cb94f80bedfddc472a3c027 r2 |
| 42000-43000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 94e5e4e7a94948ec9cc741897ed013f3 r1 |
| 42000-43000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 35b3b8ca1c9944218efd000a6057366e r2 |
| 42000-43000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 94e5e4e7a94948ec9cc741897ed013f3 r2 |
| 43000-44000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 45ba5c5f58af4cb59100a8c37f3c43b0 r1 |
| 43000-44000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 01f56bfd2f2047c0835d18fde446528e r2 |
| 43000-44000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 45ba5c5f58af4cb59100a8c37f3c43b0 r2 |
| 44000-45000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 41b5694c005540cfa0704d8192a4f160 r1 |
| 44000-45000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 41b5694c005540cfa0704d8192a4f160 r2 |
| 44000-45000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | ea30fd0719be45bfa5409e7d973b01bf r2 |
| 45000-46000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 14036213d4fc4189860b817741a2fe98 r1 |
| 45000-46000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 14036213d4fc4189860b817741a2fe98 r2 |
| 45000-46000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 5eb9d4fbc1b54bdf85679f992f257a0b r2 |
| 46000-47000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | d41082d73add475b9edf0d1f01780edb r1 |
| 46000-47000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 600f11008b6744c5be0cc65bdc76e821 r2 |
| 46000-47000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | d41082d73add475b9edf0d1f01780edb r2 |
| 47000-48095 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 421d62343368427d886c3d3aa8e0679d r1 |
| 47000-48095 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 421d62343368427d886c3d3aa8e0679d r2 |
| 47000-48000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | f11c32f1f3954ef6bd69a3ed41fd1ecc r2 |
| 48000-49015 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | f035bdebfb764c4c9ba8ac89ecb45dd2 r1 |
| 48000-49000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 6c0eb9a2f900433b9e1a6e266872070b r2 |
| 48000-49015 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | f035bdebfb764c4c9ba8ac89ecb45dd2 r2 |
| 51000-52000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | fdecac37dc434ee4b7839c5cb5db7c66 r1 |
| 51000-52000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 4523ad91e76f44739f6a2aeb0ff2af28 r2 |
| 51000-52000 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | fdecac37dc434ee4b7839c5cb5db7c66 r2 |
| 52000-53005 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 1738d6610be04955bdee526d1374be90 r1 |
| 52000-53005 ms | L2 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 1738d6610be04955bdee526d1374be90 r2 |
| 52000-53000 ms | L2 | refined | scene_changed | scene_cut [accepted]: Обнаружено заметное изменение изображения. | 268f81a8d4924d67b50e543f9113eeb3 r2 |
| 54000-55000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 360af20345474278a77c214076561fc4 r1 |
| 55000-65000 ms | L1 | committed | unknown | speech_present [uncertain]: В аудио слышна речь человека. | 272a112c909a44f3a4fd72a818785c4b r2 |
| 55000-56005 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 32d25dcdb31f4a32a2eb4a3e254ba192 r1 |
| 56000-57085 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 7179e3592f0943fb84897b82ad5f4faa r1 |
| 57000-58000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 5c336543a31a40ffb47821f19c3e6dfb r1 |
| 60000-61085 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | d323cf6475024d0586006c9b50f13517 r1 |
| 61000-62055 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | bb369c4198114423b4f83a6c08748af4 r1 |
| 63000-64000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | a15f7f9eeb044cb18349f1af0fe444c6 r1 |
| 69000-70000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | c56e4c3ffc15499caa4d1c2ee71d3737 r1 |
| 70000-90000 ms | L1 | committed | unknown | music_present [uncertain]: В аудио слышна музыка. | 33f8e7195dbe41c096c74d64c7a1a2e1 r4 |
| 72000-73055 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 21dd2d71c89e483eae53c6fa7fa53ab2 r1 |
| 73000-74000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 62b84781ba424acea537f02b06756c56 r1 |
| 75000-90000 ms | L1 | committed | unknown | speech_present [uncertain]: В аудио слышна речь человека. | 43e1a5004e364d609fcda5eca0040159 r3 |
| 76000-77000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | ebd79d50c30848bc9595c2fb2d196ba9 r1 |
| 77000-78015 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 19b3b30dd51143c3a111ca2ad9ee947e r1 |
| 78000-79045 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 4ebcb97bfbbb4a3cb6404076a8e836a0 r1 |
| 80000-81000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 2e9aea9fd8164c1abac21fc6be065272 r1 |
| 81000-82015 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 9a3f22b392484eecb732829c93f17a4f r1 |
| 83000-84065 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | f9413e872d9747c1b8c43bdb468dd0cf r1 |
| 84000-85000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | f77257c4adc8427ebb129801a0ad9b98 r1 |
| 85000-86000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 77a72d96b0c84ab0825d4c55a1af13d8 r1 |
| 86000-87000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 6d6b594bcf62464ca321f8a4d3c0ab86 r1 |
| 87000-88015 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 4324bdc6a8674115b1618488d0c32f87 r1 |
| 88000-89000 ms | L1 | committed | cross_modal_coincidence | temporally_coincident [accepted]: Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 6527a1348ef04091a53416b43573c522 r1 |

## L3 captions

Qwen status counts: {('generated', 'qwen'): 8, ('fallback', 'qwen'): 9}. Most common caption (8 occurrences): Обнаружено заметное изменение изображения.

| Source range | Status | Russian caption | Cited event revisions |
|---|---|---|---|
| 1000-4000 ms | generated | Обнаружено заметное изменение изображения. | f2d8091ff7504a7db7897e7abb003a10 r2, 6bcd14d01523460690aa1df0ead517ac r2, 67ba00aeb6e245129f217169dd467c47 r2 |
| 4000-7000 ms | generated | Обнаружено заметное изменение изображения. | 775cc8cbe6aa451c8391a3336e80dbe2 r2, 9f3b60ddf8d149d4a5a013388fab83b4 r2, 6b78506abc0b4635acbbcac9dc56d23c r2 |
| 7000-20000 ms | generated | Обнаружено заметное изменение изображения. | 4dac8b7b13d54d61897d543d7e9e33b7 r2, 41b0bf430be942b48caa3d75259fd734 r2, 3f0a07540d27408484e7b57e5d4e04ee r2 |
| 23000-33000 ms | generated | Обнаружено заметное изменение изображения. | 7914c301631f4a1ebbe6cbefd47ddf78 r2, a5911d6f5e564c90be7c9ca126810883 r2, b22aa50622124ec883024a659801c10c r2 |
| 38000-41000 ms | generated | Обнаружено заметное изменение изображения. | 206292072df64a43be183071e05b34ca r2, 1968eca49fd8470996793b9e218d3123 r2, dc8fd397ce83446da57863d3d805fb50 r2 |
| 41000-44000 ms | generated | Обнаружено заметное изменение изображения. | 31328796b0f640bda9c954503ddd0622 r2, 35b3b8ca1c9944218efd000a6057366e r2, 01f56bfd2f2047c0835d18fde446528e r2 |
| 44000-47000 ms | generated | Обнаружено заметное изменение изображения. | ea30fd0719be45bfa5409e7d973b01bf r2, 5eb9d4fbc1b54bdf85679f992f257a0b r2, 600f11008b6744c5be0cc65bdc76e821 r2 |
| 47000-52000 ms | generated | Обнаружено заметное изменение изображения. | f11c32f1f3954ef6bd69a3ed41fd1ecc r2, 6c0eb9a2f900433b9e1a6e266872070b r2, 4523ad91e76f44739f6a2aeb0ff2af28 r2 |
| 1000-53000 ms | fallback | Обнаружено заметное изменение изображения. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 268f81a8d4924d67b50e543f9113eeb3 r2, 3183aff5850943419478cb8eed8df589 r2, f9cf8d47010a4e20b0fb6ca1c87f174c r2 |
| 3000-6025 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | d819a1b1ef444ab09c8f218b3acebca2 r2, 1d01c12ef21f4cabbcc30a7993bbb9ec r2, 4760cb4ec8fd4181a7e64d68c7ebfe31 r2 |
| 6000-15055 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 3370bfc2a9b24f5aa5458a01f8eb78f2 r2, 28afcdca479f4fecbd0abdec13646006 r2, bb75e2f4ea4d4d4d94171efcb38e9297 r2 |
| 19000-26025 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 6468ad1d729e4c9281478f8ba315ae8c r2, 2daf29f9e5224e4ba0a478768045e732 r2, 504a647dc9a2493aba31b08e4aebda90 r2 |
| 32000-40075 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | cb01a67fd21e4d509fa8b9476502f01a r2, 8a5ca9e02f554a32b291e10674d4eee2 r2, 6c0d574ef0bf48c5b6f5b32c56766834 r2 |
| 40000-43000 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | c24928ab47aa4bae8f0dcd3b2df17bbb r2, e37f172d8cb94f80bedfddc472a3c027 r2, 94e5e4e7a94948ec9cc741897ed013f3 r2 |
| 43000-46000 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | 45ba5c5f58af4cb59100a8c37f3c43b0 r2, 41b5694c005540cfa0704d8192a4f160 r2, 14036213d4fc4189860b817741a2fe98 r2 |
| 46000-49015 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | d41082d73add475b9edf0d1f01780edb r2, 421d62343368427d886c3d3aa8e0679d r2, f035bdebfb764c4c9ba8ac89ecb45dd2 r2 |
| 51000-53005 ms | fallback | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. | fdecac37dc434ee4b7839c5cb5db7c66 r2, 1738d6610be04955bdee526d1374be90 r2 |

## ASR and coverage

Unique speech windows: 5; latest statuses: {'final': 5}; non-empty transcript text: 5/5; dropped: 0. speech_segments.csv retains every partial/final revision.

| Source range | Status | Text | Error |
|---|---|---|---|
| 0-20000 ms | final | о, guy stolkng  ni. Stop by fald. |  |
| 20000-40000 ms | final | Да. |  |
| 40000-60000 ms | final | а. |  |
| 60000-80000 ms | final | r you ready, Cose you ready your Rockstar. s  lok in boly. we chut have about th |  |
| 80000-90000 ms | final | Will det's perfect. Rlly one! All Systems go! Ya yo! go! goo! |  |

Final watermarks: {"C": 90000, "D": {"L1": 90000, "L2": 90000, "L3": 90000}, "E": 90000, "R": {"L1": 90000, "L2": 90000, "L3": 90000}, "epoch": 0, "issues": [{"end_ms": 5000, "level": null, "modality": "video", "reason": "embedding_stride", "revision": 1, "stage": "E", "start_ms": 1, "status": "skipped"}, {"end_ms": 25000, "level": null, "modality": "video", "reason": "runtime_backpressure", "revision": 1, "stage": "E", "start_ms": 5001, "status": "skipped"}, {"end_ms": 45000, "level": null, "modality": "video", "reason": "embedding_stride", "revision": 1, "stage": "E", "start_ms": 25001, "status": "skipped"}, {"end_ms": 65000, "level": null, "modality": "video", "reason": "embedding_stride", "revision": 1, "stage": "E", "start_ms": 45001, "status": "skipped"}, {"end_ms": 85000, "level": null, "modality": "video", "reason": "embedding_stride", "revision": 1, "stage": "E", "start_ms": 65001, "status": "skipped"}, {"end_ms": 90000, "level": null, "modality": "video", "reason": "embedding_stride", "revision": 1, "stage": "E", "start_ms": 85001, "status": "skipped"}, {"end_ms": 90000, "level": "L2", "modality": null, "reason": "runtime_backpressure", "revision": 1, "stage": "D", "start_ms": 0, "status": "skipped"}, {"end_ms": 90000, "level": "L2", "modality": null, "reason": "runtime_backpressure", "revision": 1, "stage": "R", "start_ms": 0, "status": "skipped"}, {"end_ms": 1000, "level": "L3", "modality": null, "reason": "no_supported_claim_in_interval", "revision": 1, "stage": "R", "start_ms": 0, "status": "skipped"}, {"end_ms": 90000, "level": "L3", "modality": null, "reason": "no_supported_claim_in_interval", "revision": 1, "stage": "R", "start_ms": 53005, "status": "skipped"}], "lag_ms": {"L1": 0, "L2": 0, "L3": 0}, "modality_cursors": {"audio": {"C": 90000, "E": 90000}, "speech": {"C": 90000, "E": 90000}, "video": {"C": 90000, "E": 90000}}, "stream_id": "tears_of_steel_120_210s-20261026T115307321222Z"}

Coverage issues:

- stage=D, level=L2, modality=-, reason=runtime_backpressure: 1 range(s)
- stage=E, level=-, modality=video, reason=embedding_stride: 5 range(s)
- stage=E, level=-, modality=video, reason=runtime_backpressure: 1 range(s)
- stage=R, level=L2, modality=-, reason=runtime_backpressure: 1 range(s)
- stage=R, level=L3, modality=-, reason=no_supported_claim_in_interval: 2 range(s)

## Reading the result

The run produces Russian event and caption strings, but the captions are repetitive scene-change descriptions and do not describe dialogue, music development, or instruments. ASR returned non-empty text for 5/5 unique windows; this is raw model output and transcript accuracy has not been independently rated. Uncertain semantic claims remain visible but are not verified facts. This is a quality assessment, not a positive accuracy result.

Machine-readable files: [../poc_real_90s_asr_recheck_20261026/timeline.jsonl](../poc_real_90s_asr_recheck_20261026/timeline.jsonl), semantic_match_scores.csv, events_l1_l2_latest.csv, captions_l3.csv, speech_segments.csv.
