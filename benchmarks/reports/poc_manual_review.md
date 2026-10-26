# Full L0–L3 PoC review

Run date: 2026-10-25. All eight local fixture assets were run through the CPU-only CLI with `--levels L0,L1,L2,L3`, offline model loading, four threads, and a local embedding cache. Each JSONL was checked for parseable records, final watermarks, caption schema validity, and exact caption-to-L2 revision references.

## Fixture review

| Fixture | Input label / modality | Result in JSONL | Review |
|---|---|---|---|
| `av_sync_20s.mp4` | Synthetic four-part AV sequence | 32 window matches, 36 event revisions, 1 caption citing 3 L2 revisions | Scene-cut evidence produced the caption. Music detail axes were gated while music presence remained uncertain. L3 explicitly skipped the uncovered beginning and ending. |
| `audio_music_10s.wav` | Synthetic 440/660 Hz tones with amplitude modulation | No caption; 12 event revisions | `music_absent` was the top presence candidate but remained uncertain in both windows. No instrument or music claim was published. |
| `audio_silence_5s.wav` | Digital silence | No caption | Semantic candidates abstained; no speech/music claim was published. |
| `audio_sine_5s.wav` | Synthetic 440 Hz sine wave | No caption | The tone did not pass semantic acceptance; output remained uncertain/unknown. |
| `audio_speech_ru.wav` | Locally generated Russian TTS | No caption; 9 event revisions | Speech presence was accepted in one window but did not persist across two windows. ASR is disabled in this profile, so no transcript was invented. |
| `video_scene_cuts_8s.mp4` | Four solid-color scenes with hard cuts | 1 caption citing 3 L2 revisions | The caption came from accepted measured scene-cut events; uncertain scene labels were not used. |
| `video_motion_8s.mp4` | Synthetic moving test pattern | 2 captions citing 3 and 2 L2 revisions | Captions used accepted scene-change detector claims. They do not identify the pattern as a real-world action. |
| `video_static_3s.mp4` | Static solid-color scene | No caption | Scene candidates remained uncertain; no visual description was promoted. |

## Cross-run checks

- All emitted captions validate against `configs/schemas/narration_v1.schema.json`.
- Every caption's `(event_id, revision)` resolves to an emitted L2 event revision in the same JSONL.
- Final `C`, `E`, `R[L1]`, `R[L2]`, and `R[L3]` reached each fixture's media horizon. `skipped`, `unavailable`, and embedding-stride intervals remain listed in watermark issues.
- The JSONL contains intermediate watermark records; the CLI also prints `C`, `E`, `R` and backlog to stderr while processing.
- In the 20-second AV run, the warm-cache end-to-end time was 14.83 s; profile candidate embeddings took 11.76 s and video decode/features/embed/match took 15.59 s in the earlier cold run. This is a smoke result, not a real-time claim.
- Ruff passed, mypy passed for 34 source files, and pytest passed all 107 tests, including five REST/WebSocket API integration tests.

## Provisional music and visual abstention counts

The eight fixture timelines contain 76 semantic `window_match` rows after filtering to the audio and image modalities. These are candidate-window decisions, not independent natural-media examples or final temporal events.

| Scope | Window decisions | Accepted | Uncertain / abstained | Precision |
|---|---:|---:|---:|---|
| Audio `music_presence` axis | 10 | 0 | 10 (100%) | Undefined: no accepted predictions |
| All audio axes | 40 | 1 | 39 (97.5%) | Not a useful estimate: the sole accepted row is synthetic TTS `speech_present` |
| All visual semantic axes | 36 | 0 | 36 (100%) | Undefined: no accepted predictions |

No music-presence or visual-semantic claim was accepted in these synthetic runs, so there were no accepted false positives against the fixture labels. That does not establish 100% precision: there are no accepted positive music or visual predictions from which to estimate precision. The only accepted audio row was speech presence on the locally generated eSpeak TTS fixture. L0 scene-cut detector events are excluded because they are not semantic visual claims.

These counts document observed abstention behavior on the current synthetic fixtures only. Natural-media precision, recall, and calibration still require independently reviewed positive and negative windows.

## Limits found

These fixtures are generated tones, TTS, silence, color cuts, and test patterns, not natural recordings. They do not validate instrument-family recognition, environmental-noise categories, natural actions, or real speech transcription. The music gate and semantic thresholds are still provisional; this review confirms honest abstention and provenance on the available local fixtures, not recognition accuracy on field footage. The file-mode L2/L3 pass runs after media evidence collection; the asynchronous queue API remains a separate worker component.
