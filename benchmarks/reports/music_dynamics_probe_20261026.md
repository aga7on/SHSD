# Music development probe

## Method and limits

Scored the seven current music-profile axes independently on the same 18 five-second windows from the 90-second Tears of Steel excerpt. This intentionally bypassed the production gate so the detail axes could be inspected even when music presence was uncertain. The scores are not probabilities, and no independently reviewed labels were available.

The production gate still requires accepted music_present before detail claims can be emitted. Music presence was uncertain in all 18 windows, so the actual L1/L2/L3 run emitted no accepted music-development event.

## Window score summary

| Axis | Mean best cosine | Mean top-two gap | Accepted windows under current policy | Top-ranked candidate counts |
|---|---:|---:|---:|---|
| music_presence | 0.736320 | 0.009565 | 0/18 | present 8, absent 10 |
| vocal_presence | 0.742320 | 0.037153 | 4/18 | vocals present 6, absent 12 |
| percussion_presence | 0.725770 | 0.012387 | 0/18 | present 4, absent 14 |
| bass_presence | 0.724690 | 0.007822 | 0/18 | present 15, not distinct 3 |
| energy | 0.749886 | 0.036385 | 7/18 | high 5, low 13 |
| tempo_feel | 0.742003 | 0.013117 | 0/18 | fast 7, slow 11 |
| instrument_family | 0.716774 | 0.009976 | 14/18 | acoustic strings 11, electronic 3, percussion 4 |

The profile has mutually exclusive tests for vocals, percussion, bass, energy, and tempo. Instrument family is non-exclusive: 14 windows passed at least one candidate and individual candidate support overlapped heavily (acoustic strings 14 windows, electronic timbre 13, percussion timbre 13). This is not enough to identify which instrument is present.

Top-candidate identities changed between adjacent windows 7 times for music presence, 3 for vocals, 1 for percussion, 4 for bass, 7 for energy, 4 for tempo feel, and 9 for instrument family. These are changes in embedding rankings only; they are not verified musical transitions.

## Measured audio changes

The existing five-second signal pass found loudness from -33.983 to -12.062 dBFS and spectral centroid from 674.34 to 1745.76 Hz. Its energy-active fraction was 1.0 in every window. The onset feature ranged from 272 to 482 per window; it is not a BPM estimate. The measurements show changing audio energy and spectrum, but do not identify an instrument entry, rhythm change, or vocal entrance.

## Result

The current system cannot yet describe the musical development of this clip. It does not establish an instrument entry, a reliable rhythm change, or a vocal transition; music presence remains uncertain and blocks all detail axes in production. The 14/18 instrument-family support with strong candidate overlap also points to poor category separation. Keep the thresholds and profile unchanged pending independent labels.

Per-window rankings and scores are in music_dynamics_probe_20261026/music_dynamics_prompt_scores.csv. The exact candidates, score distributions, and ranking-change timestamps are in music_dynamics_probe_20261026/music_dynamics_probe.json.
