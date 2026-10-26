# Temporal audio L2 refinement on the real 90-second video

## Run

- Source: `X:\AI\SHSD\benchmarks\fixtures\real_poc\tears_of_steel_120_210s.mp4`; duration 90.000 s; CPU, 4 threads; 5-second windows.
- Levels: L0/L1/L2; L3 and ASR disabled for this focused L2 recheck. The earlier full L1/L2/L3 pass is in [`real_video_quality_asr_recheck_20261026/report_real_video_quality.md`](../real_video_quality_asr_recheck_20261026/report_real_video_quality.md).
- Embedding model revision: `914f7f89142e33e77833254d9c9b90c3cef7303b`; match thresholds: cosine >= 0.60 and margin >= 0.05.
- End-to-end elapsed: 53.386 s; latest committed/refined events: L1=64, L2=62.

## L2 semantic checks

L2 re-ran each eligible audio candidate against its source-time audio embeddings, then matched a normalized mean of the in-event embeddings using the same candidate vectors and the same similarity/margin policy. It required at least two matching in-event windows. Adjacent windows are retained as before/after context. The matcher never lowers thresholds.

- L2 checks: 62 total: 0 confirmed, 10 abstained, 52 skipped.
- Candidate checks: 10 semantic rechecks; 0 confirmed, 10 abstained. Axes evaluated: {'speech_presence': 4, 'music_presence': 4, 'ambient_sound': 1, 'impact_sound': 1}.
- The ten audio rechecks remained `uncertain`: the selected candidate matched again, but aggregate margins were 0.007?0.021, below the configured 0.05. This agrees with the observed semantic-matcher uncertainty and does not justify lowering the margin without independent labels.
- The other 52 L2 events had no matching audio-axis provenance or were non-audio events; those were skipped with a visible reason.

| Event | Axis | Candidate | Aggregate candidate | Decision | Cosine | Margin | In-event target votes |
|---|---|---|---|---|---:|---:|---:|
| 63b81e3f8a884a0fbcfdf1a707fa33c9 | speech_presence | speech_absent | speech_absent | uncertain | 0.734 | 0.007 | 2 |
| fa5f975027c440ba9d2ad186226d2a90 | music_presence | music_absent | music_absent | uncertain | 0.749 | 0.013 | 2 |
| 884a19c032464215afc8b26676b4288b | ambient_sound | ambient_sound_present | ambient_sound_present | uncertain | 0.831 | 0.021 | 8 |
| b2fa76d7feac4867a150f9194539b245 | impact_sound | impact_present | impact_present | uncertain | 0.822 | 0.019 | 8 |
| 423552ebcbf44222ba02131487d89743 | speech_presence | speech_present | speech_present | uncertain | 0.781 | 0.015 | 2 |
| 436d3a2ba444458aae1869685099f0a7 | music_presence | music_absent | music_absent | uncertain | 0.782 | 0.011 | 3 |
| 1f2a160602b14dbcb3830705c8167b49 | speech_presence | speech_absent | speech_absent | uncertain | 0.741 | 0.011 | 2 |
| ab3d6c5605354ddfb1f97469bc579e55 | music_presence | music_present | music_present | uncertain | 0.769 | 0.009 | 2 |
| 503cf53b7a9d4d66a2749d2f82cab5d7 | speech_presence | speech_absent | speech_absent | uncertain | 0.753 | 0.011 | 4 |
| dfe6646102ef4adc803e634d209fb8af | music_presence | music_absent | music_absent | uncertain | 0.782 | 0.008 | 4 |

## Every latest L1/L2 event and Russian claim text

Rows below select the newest committed L1 and L2 revision for each event id. `uncertain` claims stay visible as hypotheses, not verified facts. The full event revisions and per-window L2 scores are in [`events.jsonl`](events.jsonl); a spreadsheet-ready export is in [`events_l1_l2_latest.csv`](events_l1_l2_latest.csv).

| Level | Time | Kind | State | Claim | Decision | Cosine | Margin | Samples | Russian description |
|---|---|---|---|---|---|---:|---:|---:|---|
| L1 | 00:00.000?00:10.000 | unknown | committed | speech_absent | uncertain | 0.729 | 0.003 | 2 | В аудио не слышно речи человека. |
| L1 | 00:00.000?00:10.000 | unknown | committed | music_absent | uncertain | 0.744 | 0.009 | 2 | В аудио не слышно музыки. |
| L2 | 00:00.000?00:10.000 | unknown | committed | speech_absent | uncertain | 0.729 | 0.003 | 2 | В аудио не слышно речи человека. |
| L2 | 00:00.000?00:10.000 | unknown | committed | music_absent | uncertain | 0.744 | 0.009 | 2 | В аудио не слышно музыки. |
| L1 | 00:00.000?01:30.000 | unknown | committed | ambient_sound_present | uncertain | 0.758 | 0.002 | 18 | Слышен непрерывный фоновый звук окружающей среды. |
| L1 | 00:00.000?01:30.000 | unknown | committed | impact_present | uncertain | 0.750 | 0.001 | 18 | Слышен один или несколько коротких ударных звуков. |
| L2 | 00:00.000?01:30.000 | unknown | committed | ambient_sound_present | uncertain | 0.758 | 0.002 | 18 | Слышен непрерывный фоновый звук окружающей среды. |
| L2 | 00:00.000?01:30.000 | unknown | committed | impact_present | uncertain | 0.750 | 0.001 | 18 | Слышен один или несколько коротких ударных звуков. |
| L1 | 00:01.000?00:02.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:01.000?00:02.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:01.000?00:02.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:02.000?00:03.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:02.000?00:03.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L2 | 00:02.000?00:03.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:03.000?00:04.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:03.000?00:04.015 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:03.000?00:04.015 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:04.000?00:05.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:04.000?00:05.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:04.000?00:05.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L2 | 00:05.000?00:06.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:05.000?00:06.025 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:05.000?00:06.025 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:06.000?00:07.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:06.000?00:07.015 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:06.000?00:07.015 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:07.000?00:08.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:07.000?00:08.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L2 | 00:07.000?00:08.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:10.000?00:20.000 | unknown | committed | speech_present | uncertain | 0.743 | 0.010 | 2 | В аудио слышна речь человека. |
| L2 | 00:10.000?00:20.000 | unknown | committed | speech_present | uncertain | 0.743 | 0.010 | 2 | В аудио слышна речь человека. |
| L2 | 00:14.000?00:15.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:14.000?00:15.055 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:14.000?00:15.055 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:15.000?00:30.000 | unknown | committed | music_absent | uncertain | 0.733 | 0.004 | 3 | В аудио не слышно музыки. |
| L2 | 00:15.000?00:30.000 | unknown | committed | music_absent | uncertain | 0.733 | 0.004 | 3 | В аудио не слышно музыки. |
| L1 | 00:17.208?00:32.208 | unknown | committed | screen_text_visible | uncertain | 0.609 | 0.004 | 2 | На изображении виден читаемый текст. |
| L2 | 00:17.208?00:32.208 | unknown | committed | screen_text_visible | uncertain | 0.609 | 0.004 | 2 | На изображении виден читаемый текст. |
| L1 | 00:17.208?00:52.208 | unknown | committed | indoor_setting | uncertain | 0.632 | 0.010 | 4 | На изображении показано помещение. |
| L1 | 00:17.208?00:52.208 | unknown | committed | person_visible | uncertain | 0.630 | 0.019 | 4 | На изображении виден человек. |
| L2 | 00:17.208?00:52.208 | unknown | committed | indoor_setting | uncertain | 0.632 | 0.010 | 4 | На изображении показано помещение. |
| L2 | 00:17.208?00:52.208 | unknown | committed | person_visible | uncertain | 0.630 | 0.019 | 4 | На изображении виден человек. |
| L2 | 00:19.000?00:20.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:19.000?00:20.105 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:19.000?00:20.105 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:20.000?00:30.000 | unknown | committed | speech_absent | uncertain | 0.729 | 0.007 | 2 | В аудио не слышно речи человека. |
| L2 | 00:20.000?00:30.000 | unknown | committed | speech_absent | uncertain | 0.729 | 0.007 | 2 | В аудио не слышно речи человека. |
| L2 | 00:23.000?00:24.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:23.000?00:24.045 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:23.000?00:24.045 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:25.000?00:26.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:25.000?00:26.025 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:25.000?00:26.025 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:27.208?00:42.208 | unknown | committed | unknown | uncertain | 0.596 | 0.000 | 2 | ? |
| L2 | 00:27.208?00:42.208 | unknown | committed | unknown | uncertain | 0.596 | 0.000 | 2 | ? |
| L1 | 00:30.000?00:40.000 | unknown | committed | music_present | uncertain | 0.754 | 0.006 | 2 | В аудио слышна музыка. |
| L2 | 00:30.000?00:40.000 | unknown | committed | music_present | uncertain | 0.754 | 0.006 | 2 | В аудио слышна музыка. |
| L2 | 00:32.000?00:33.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:32.000?00:33.055 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:32.000?00:33.055 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:35.000?00:55.000 | unknown | committed | speech_absent | uncertain | 0.732 | 0.002 | 4 | В аудио не слышно речи человека. |
| L2 | 00:35.000?00:55.000 | unknown | committed | speech_absent | uncertain | 0.732 | 0.002 | 4 | В аудио не слышно речи человека. |
| L2 | 00:38.000?00:39.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:38.000?00:39.055 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:38.000?00:39.055 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:39.000?00:40.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:39.000?00:40.075 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:39.000?00:40.075 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:40.000?00:41.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:40.000?00:41.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:40.000?00:41.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:40.000?01:00.000 | unknown | committed | music_absent | uncertain | 0.767 | 0.006 | 4 | В аудио не слышно музыки. |
| L2 | 00:40.000?01:00.000 | unknown | committed | music_absent | uncertain | 0.767 | 0.006 | 4 | В аудио не слышно музыки. |
| L1 | 00:41.000?00:42.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:41.000?00:42.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L2 | 00:41.000?00:42.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:42.000?00:43.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:42.000?00:43.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L2 | 00:42.000?00:43.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:43.000?00:44.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:43.000?00:44.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L2 | 00:43.000?00:44.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:44.000?00:45.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:44.000?00:45.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L2 | 00:44.000?00:45.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:45.000?00:46.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:45.000?00:46.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:45.000?00:46.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:46.000?00:47.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:46.000?00:47.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L2 | 00:46.000?00:47.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:47.000?00:48.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:47.000?00:48.095 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:47.000?00:48.095 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:48.000?00:49.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L1 | 00:48.000?00:49.015 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:48.000?00:49.015 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:51.000?00:52.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L2 | 00:51.000?00:52.000 | scene_changed | refined | scene_cut | accepted | ? | ? | 1 | Обнаружено заметное изменение изображения. |
| L2 | 00:51.000?00:52.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:52.000?00:53.005 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:54.000?00:55.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:55.000?00:56.005 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:55.000?01:05.000 | unknown | committed | speech_present | uncertain | 0.763 | 0.002 | 2 | В аудио слышна речь человека. |
| L1 | 00:56.000?00:57.085 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 00:57.000?00:58.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:00.000?01:01.085 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:01.000?01:02.055 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:03.000?01:04.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:04.458?01:19.458 | unknown | committed | unknown | uncertain | 0.596 | 0.000 | 2 | ? |
| L1 | 01:09.000?01:10.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:10.000?01:30.000 | unknown | committed | music_present | uncertain | 0.689 | 0.009 | 4 | В аудио слышна музыка. |
| L1 | 01:12.000?01:13.055 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:13.000?01:14.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:15.000?01:30.000 | unknown | committed | speech_present | uncertain | 0.727 | 0.012 | 3 | В аудио слышна речь человека. |
| L1 | 01:16.000?01:17.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:17.000?01:18.015 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:18.000?01:19.045 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:20.000?01:21.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:21.000?01:22.015 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:23.000?01:24.065 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:24.000?01:25.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:25.000?01:26.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:26.000?01:27.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:27.000?01:28.015 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |
| L1 | 01:28.000?01:29.000 | cross_modal_coincidence | committed | temporally_coincident | accepted | ? | ? | 1 | Смена кадра совпадает по времени с обнаруженным звуковым началом; причинная связь не установлена. |

## Files

- `events.jsonl`: all emitted analysis, L1/L2 events, L2 per-window comparisons, and final metrics.
- `events_l1_l2_latest.csv`: latest L1/L2 descriptions and score fields.
- `report.md`: this readable run summary and complete event table.
