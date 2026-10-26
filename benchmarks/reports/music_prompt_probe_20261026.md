# Semantic Matcher music-prompt probe

## Method

Compared four music-presence prompt pairs on the same 18 non-overlapping, five-second audio windows from the 90-second Tears of Steel excerpt. The pinned EmbeddingGemma 2 audio encoder produced both audio and text vectors. The existing policy stayed at minimum cosine 0.60 and minimum top-candidate margin 0.05.

Cosines are not probabilities. This diagnostic has no independently reviewed labels and makes no accuracy claim.

## Results

| Prompt pair | Mean positive cosine | Mean negative cosine | Mean absolute gap | Median absolute gap | Accepted by current policy | Positive / negative top rank |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 0.732380 | 0.732023 | 0.009526 | 0.008363 | 0/18 | 8 / 10 |
| performance vs speech/noise | 0.726692 | 0.715349 | 0.013952 | 0.013757 | 0/18 | 15 / 3 |
| tune/beat vs words/noise | 0.748885 | 0.745380 | 0.022587 | 0.022063 | 1/18 | 11 / 7 |
| soundtrack vs dialogue/effects | 0.731806 | 0.728813 | 0.021554 | 0.019540 | 0/18 | 11 / 7 |

For the baseline pair, the present-candidate score ranged 0.674119-0.769977 and the absent-candidate score ranged 0.654951-0.774973. Every best score passed 0.60, but every baseline window stayed below the 0.05 margin. The current uncertainty is therefore caused by near-ties between the opposing text hypotheses on this clip, not by scores falling below the minimum similarity.

The tune_beat_vs_words_and_noise pair produced one accepted result at 10-15 seconds, with music_absent ahead by 0.055271. The other windows stayed uncertain. Alternative wording changed the margin and sometimes changed the top candidate; without reviewed labels this does not establish that any wording is more correct.

## Exact prompt pairs

- **Baseline:** “Music is audible in the audio.” / “No music is audible in the audio.”
- **Performance vs speech/noise:** “An instrumental or sung musical performance is audible, with melody or rhythm.” / “Only speech, effects, or environmental sounds are audible; there is no musical performance.”
- **Tune/beat vs words/noise:** “The audio contains a song or instrumental music, with a tune, beat, or playing instruments.” / “The audio contains spoken words or everyday noises, without a tune, beat, or instrumental playing.”
- **Soundtrack vs dialogue/effects:** “A musical soundtrack is playing under or alongside the other sounds.” / “There is no soundtrack or music, only dialogue and natural sound effects.”

## Decision

Keep production wording and both thresholds unchanged until independently reviewed labels are available. The probe supports a prompt-contrast problem for music on these windows; it does not tell us which candidate is correct. The full per-window cosine values are in music_prompt_probe_20261026/music_prompt_scores.csv, with model revision and prompt text in music_prompt_probe_20261026/music_prompt_probe.json.
