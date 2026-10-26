# Natural audio A/B for iterative `speech_presence`

## Purpose and scope

This offline, evaluation-only sample compares the fixed `speech_presence` axis with one opt-in Qwen proposal pass. It is not training data. It contains 40 manually assigned, five-second windows from 11 independent recordings: 20 speech-positive (14 archival speech, three group-discussion windows, three speech-over-market windows) and 20 speech-negative (10 piano, three choir, four rain/wind, three urban-rain windows).

This remains exploratory, not representative. Most speech is archival English, conversational and speech-over-noise coverage each comes from one short source, and the negatives still contain only piano, choral singing, weather, wind chimes, and rainy street ambience. Interval labels were assigned from source descriptions; the new intervals have not been independently reviewed by listening. The F3.03 representative-evaluation DoD remains open.

## Inputs and provenance

The manifest records source pages, licenses, time intervals, attribution, and SHA-256 hashes. The build script verifies every local asset before decoding and writes mono 16 kHz PCM inputs from exact five-second intervals. The three urban-street excerpts are stored as small derived clips because the original long FLAC has timestamp gaps; each manifest entry records its source offset and transformation. `build_report.json` records input hashes, and `expected_segments.jsonl` records each interval label and rationale.

| Added source | License / provenance | Use |
|---|---|---|
| [Group discussion 1.ogg](https://commons.wikimedia.org/wiki/File:Group_discussion_1.ogg) | Public domain by recording author ezwa. | Natural group conversation; three separated windows. |
| [Christmas market in Ljubljana, part 3](https://commons.wikimedia.org/wiki/File:Christmas_market_in_Ljubljana_city_centre_-_part_3.webm) | CC BY 3.0. Credit: Sounds of Changes; sound recording Du?an Oblak; video recording Barbara Rezar Grilc; photo Irena Maru?i?. Audio-only five-second excerpts are decoded and converted to mono 16 kHz PCM. | People talking with adverts and loudspeaker music; three windows. |
| [Christian mass singing hallelujah.ogg](https://commons.wikimedia.org/wiki/File:Christian_mass_singing_hallelujah.ogg) | Public domain by recording author stephan. | Choir and organ; singing is labeled as vocal music, not spoken speech; three windows. |
| [Urban Street on a Rainy Afternoon.flac](https://commons.wikimedia.org/wiki/File:Urban_Street_on_a_Rainy_Afternoon.flac) | CC0 1.0 by Extemporalist. | Three five-second excerpts of traffic, rain, and crows at 1:00, 10:00, and 20:00. |

## Reproduce

Build deterministic inputs and labels after the local source assets are present. This step requires no network access:

```powershell
python scripts/build_iterative_eval_corpus.py
```

Run each corpus with the same pinned local CPU embedding model and thresholds. `--offline` prevents model downloads; `--iterative-axis speech_presence` enables the bounded proposal pass:

```powershell
.\.venv\Scripts\shsd.exe analyze benchmarks\evaluation\iterative_speech_presence_natural\inputs\speech_present.wav --levels L0,L1 --cpu-only --offline --threads 4 --window-seconds 5 --iterative-axis speech_presence --stream-id natural-speech-present --output benchmarks\reports\iterative_speech_presence_natural\speech_present.jsonl
.\.venv\Scripts\shsd.exe analyze benchmarks\evaluation\iterative_speech_presence_natural\inputs\instrumental_music.wav --levels L0,L1 --cpu-only --offline --threads 4 --window-seconds 5 --iterative-axis speech_presence --stream-id natural-instrumental-music --output benchmarks\reports\iterative_speech_presence_natural\instrumental_music.jsonl
.\.venv\Scripts\shsd.exe analyze benchmarks\evaluation\iterative_speech_presence_natural\inputs\environmental_sounds.wav --levels L0,L1 --cpu-only --offline --threads 4 --window-seconds 5 --iterative-axis speech_presence --stream-id natural-environmental-sounds --output benchmarks\reports\iterative_speech_presence_natural\environmental_sounds.jsonl
```

Combine the three timelines and score them against the interval labels:

```powershell
cmd /c copy /Y /b benchmarks\reports\iterative_speech_presence_natural\speech_present.jsonl+benchmarks\reports\iterative_speech_presence_natural\instrumental_music.jsonl+benchmarks\reports\iterative_speech_presence_natural\environmental_sounds.jsonl benchmarks\reports\iterative_speech_presence_natural\iterations.jsonl
python scripts/evaluate_iterative_hypotheses.py benchmarks\reports\iterative_speech_presence_natural\iterations.jsonl benchmarks\evaluation\iterative_speech_presence_natural\expected_segments.jsonl --output benchmarks\reports\iterative_speech_presence_natural\evaluation.json
```

The evaluator ignores non-iteration rows in the timelines and matches the remaining records by stream, axis, and interval.

## Run configuration and result

- Runtime: offline CPU, four threads; EmbeddingGemma 2 revision `914f7f89142e33e77833254d9c9b90c3cef7303b`; five-second windows; levels L0/L1.
- Decision policy: cosine threshold 0.60, margin 0.05, top-k 3. Similarity is not a probability.
- Evaluator: 40/40 labeled intervals matched, zero unmatched.
- Baseline: 1/40 accepted predictions (1 correct), 2.5% coverage; top-ranked candidate correct in 24/40 windows (60.0%). By class: speech 18/20, music including choir 2/13, environmental sound 4/7.
- Iterated: same accepted and top-ranked results; no accuracy or coverage improvement.
- Qwen: three per-stream attempts returned no candidates, zero new candidates, and 9,508.305 ms aggregate proposal latency. The remaining windows used baseline-only results.

The 60.0% ranked accuracy and 2.5% coverage do not establish reliable speech detection. The new conversational and mixed-noise clips improve coverage of failure modes but are too few, and their labels are based on descriptions rather than independent listening. Keep iterative prompting opt-in. Full JSONL timelines, exact source intervals, input hashes, and aggregate metrics are stored alongside this README.
