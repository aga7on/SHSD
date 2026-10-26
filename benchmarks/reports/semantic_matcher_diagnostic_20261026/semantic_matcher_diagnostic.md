# Semantic Matcher diagnostic

- Input JSONL SHA-256: `3be9e441990185a5c57e616d1c3b05a221552a099874de8ed90a8efa31117ec1`.
- EmbeddingGemma revision: `914f7f89142e33e77833254d9c9b90c3cef7303b`; CPU threads: 4.
- Run policy: min cosine 0.6, min margin 0.05; thresholds unchanged.
- L1 rows: 100; decisions: `{'uncertain': 95, 'accepted': 5}`.
- No labels were joined. The existing 40-clip speech pack is described as `source-description-derived; not independently reviewed by listening`; it is not gold for music-prompt tuning.

## Real-window score and abstention distributions

| Axis | Rows | Decisions | Best cosine min / median / max | Runner-up median | Margin min / median / mean / max | Uncertain below / above cosine floor |
|---|---:|---|---|---:|---|---:|
| `ambient_sound` | 18 | `{'uncertain': 18}` | 0.678 / 0.779 / 0.812 | 0.768 | 0.002 / 0.018 / 0.019 / 0.043 | 0 / 18 |
| `impact_sound` | 18 | `{'uncertain': 18}` | 0.699 / 0.761 / 0.788 | 0.753 | 0.001 / 0.019 / 0.018 / 0.045 | 0 / 18 |
| `music_presence` | 18 | `{'uncertain': 14, 'accepted': 4}` | 0.728 / 0.761 / 0.796 | 0.749 | 0.004 / 0.014 / 0.026 / 0.082 | 0 / 14 |
| `person_presence` | 7 | `{'uncertain': 7}` | 0.617 / 0.624 / 0.640 | 0.595 | 0.019 / 0.029 / 0.030 / 0.043 | 0 / 7 |
| `scene_setting` | 7 | `{'uncertain': 7}` | 0.614 / 0.632 / 0.649 | 0.610 | 0.004 / 0.005 / 0.011 / 0.039 | 0 / 7 |
| `scene_style` | 7 | `{'uncertain': 7}` | 0.572 / 0.584 / 0.594 | 0.562 | 0.000 / 0.000 / 0.000 / 0.000 | 7 / 0 |
| `screen_text_presence` | 7 | `{'uncertain': 7}` | 0.591 / 0.602 / 0.620 | 0.596 | 0.001 / 0.007 / 0.009 / 0.024 | 2 / 5 |
| `speech_presence` | 18 | `{'uncertain': 17, 'accepted': 1}` | 0.714 / 0.734 / 0.770 | 0.723 | 0.002 / 0.011 / 0.014 / 0.058 | 0 / 17 |

## Within-axis text-hypothesis similarity

| Profile | Axis | Candidates | Mean cosine | Closest pair |
|---|---|---:|---:|---|
| `av` | `audio_visual_correspondence` | 2 | 0.888 | `aligned_event` / `no_clear_alignment`: 0.888 |
| `av` | `speech_visual_correspondence` | 2 | 0.933 | `visible_speech_activity` / `no_speech_visual_alignment`: 0.933 |
| `music` | `music_presence` | 4 | 0.802 | `music_present` / `environment_dominant`: 0.833 |
| `music` | `vocal_presence` | 2 | 0.870 | `vocals_present` / `vocals_absent`: 0.870 |
| `music` | `percussion_presence` | 2 | 0.849 | `percussion_present` / `percussion_absent`: 0.849 |
| `music` | `bass_presence` | 2 | 0.926 | `bass_present` / `bass_absent`: 0.926 |
| `music` | `electronic_timbre` | 2 | 0.861 | `electronic_timbre_present` / `electronic_timbre_absent`: 0.861 |
| `music` | `energy` | 2 | 0.801 | `high_energy` / `low_energy`: 0.801 |
| `music` | `tempo_feel` | 2 | 0.890 | `fast_feel` / `slow_feel`: 0.890 |
| `music` | `instrument_family` | 4 | 0.873 | `acoustic_strings` / `piano_timbre`: 0.919 |
| `sound` | `speech_presence` | 2 | 0.821 | `speech_present` / `speech_absent`: 0.821 |
| `sound` | `ambient_sound` | 2 | 0.945 | `ambient_sound_present` / `ambient_sound_absent`: 0.945 |
| `sound` | `impact_sound` | 2 | 0.935 | `impact_present` / `impact_absent`: 0.935 |
| `visual` | `scene_setting` | 2 | 0.893 | `indoor_setting` / `outdoor_setting`: 0.893 |
| `visual` | `person_presence` | 2 | 0.871 | `person_visible` / `person_not_visible`: 0.871 |
| `visual` | `screen_text_presence` | 2 | 0.912 | `screen_text_visible` / `screen_text_absent`: 0.912 |
| `visual` | `scene_style` | 2 | 0.872 | `natural_scene` / `built_environment`: 0.872 |

## Closest text hypotheses across axes (all modalities)

| Cosine | Left | Right |
|---:|---|---|
| 0.966 | `music.electronic_timbre.electronic_timbre_present` | `music.instrument_family.electronic_timbre` |
| 0.949 | `music.electronic_timbre.electronic_timbre_absent` | `music.instrument_family.acoustic_strings` |
| 0.895 | `music.electronic_timbre.electronic_timbre_absent` | `music.instrument_family.piano_timbre` |
| 0.894 | `visual.person_presence.person_not_visible` | `visual.screen_text_presence.screen_text_absent` |
| 0.894 | `av.speech_visual_correspondence.no_speech_visual_alignment` | `sound.speech_presence.speech_absent` |
| 0.877 | `music.energy.high_energy` | `music.tempo_feel.fast_feel` |
| 0.876 | `music.electronic_timbre.electronic_timbre_absent` | `music.instrument_family.electronic_timbre` |
| 0.874 | `music.electronic_timbre.electronic_timbre_present` | `music.instrument_family.piano_timbre` |
| 0.872 | `music.music_presence.environment_dominant` | `sound.ambient_sound.ambient_sound_present` |
| 0.869 | `visual.scene_setting.outdoor_setting` | `visual.scene_style.natural_scene` |
| 0.867 | `music.electronic_timbre.electronic_timbre_present` | `music.instrument_family.percussion_timbre` |
| 0.865 | `music.electronic_timbre.electronic_timbre_present` | `music.instrument_family.acoustic_strings` |
| 0.865 | `visual.person_presence.person_visible` | `visual.screen_text_presence.screen_text_absent` |
| 0.864 | `visual.scene_setting.indoor_setting` | `visual.person_presence.person_visible` |
| 0.860 | `music.electronic_timbre.electronic_timbre_absent` | `music.instrument_family.percussion_timbre` |
| 0.858 | `visual.person_presence.person_visible` | `visual.screen_text_presence.screen_text_visible` |
| 0.855 | `music.music_presence.conversation_dominant` | `sound.speech_presence.speech_present` |
| 0.854 | `music.vocal_presence.vocals_absent` | `music.percussion_presence.percussion_absent` |
| 0.850 | `visual.scene_setting.outdoor_setting` | `visual.scene_style.built_environment` |
| 0.848 | `sound.speech_presence.speech_present` | `visual.person_presence.person_visible` |

## Interpretation

- Similarity and margin answer different questions. Current acceptance requires best media-to-text cosine ≥ 0.60 and a top-candidate lead ≥ 0.05.
- Uncertainty can be a margin issue even when best cosine clears the floor. Visual axes also include low-cosine cases. Cosine is not probability.
- Pairwise text cosine diagnoses prompt-bank overlap, not quality. Cross-axis pairs include audio/music/visual concepts because hypotheses share one encoder.
- This report does not tune thresholds. Use blind labels to compare per-axis precision, recall, accepted coverage, and false-positive rates.
