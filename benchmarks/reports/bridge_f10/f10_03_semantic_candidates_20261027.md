# F10.03 — Real clip semantic probes and review packet

Date: 2026-10-27. Model weights were not changed and no bridge training was run.

## What is verified

- The existing 90-second *Tears of Steel* run is the requested real music/video sample: it contains scene changes, music, and dialogue. Its report lists every emitted L1/L2 event and Russian description, plus all three Qwen L3 captions: [full L1/L2/L3 output](../music_quality_v2/real_video_quality_review_b0_graph.md). It produced 62 L1 and 62 L2 revisions, three Russian captions, zero newly accepted L2 details, 95 uncertain versus five accepted window matches, and took 27.91 seconds offline. The accepted 01:10–01:25 scene-change claim is “На первом плане слышен разговор людей.” The same timeline interval in L3 is “На первом плане слышен разговор.” These are model outputs, not independently verified labels or realtime figures.
- The positive-only scene probe on the real audio interval has four 5-second windows. At source PTS 185000–190000 ms, `music_present` is top but uncertain (cosine 0.791, margin 0.006). In the next three windows, source PTS 190000–205000 ms, `conversation_dominant` is accepted (cosines 0.746–0.754; margins 0.057–0.083). The old binary comparison accepts zero of these four windows. This shows that the positive alternatives can separate dialogue from music in this clip; it does not establish accuracy or false-positive behavior without blind labels.
- The isolated AUDIO-only run reproduces the dialogue transition. L1 and L2 place `conversation_dominant` over clip time 5000–20000 ms, corresponding to source PTS 190000–205000 ms. L2 records the scene change and adds no music details because the music premise is not confirmed. Qwen produces the Russian caption “На первом плане слышен разговор людей.” in 2308 ms. No L3 music-development description is produced.
- The 10-second VIDEO-only clip is 120000–130000 ms in the source film. A pinned, external zero-shot X-CLIP diagnostic ranks “An older man rises from the bed to stand beside it” highest for 121000–129000 ms (logit 6.1758; runner-up “A man reaches toward a candle beside the bed”, margin 0.3609). The optional EventGraph record links this candidate to eight source-time frame references. It is marked `unverified_model_hypothesis`, is not passed to Qwen, and is not part of the default `analyze` path. The score and margin are not calibrated confidence.
- A new VIDEO-only scan scores thirteen overlapping 8-second windows across source PTS 120000–140000 ms at 1-second strides. It ranks `reaches_toward_candle` in the first window, then `rises_from_bed_to_standing` in the next twelve. The latter candidate persists into late windows after the rise; its raw logit rises from 6.176 at 121000–129000 ms to 12.984 at 132000–140000 ms. Mean absolute RGB change at 128×72 resolution across each window's seven adjacent frame pairs falls from 27.80 to 11.79 over those same windows. In the final window, the 132–133 s and 133–134 s pair deltas are 6.89 and 6.88, followed by a 41.32 spike at 134–135 s. These cheap pixel deltas are not optical flow or action labels, but they expose that the rising X-CLIP score is not tracking visible motion consistently. The EventGraph stores thirteen unverified hypotheses linked to one 20-frame PTS-preserving feature sequence; narration request count remains zero.
- Review clips are checked with `ffprobe`: VIDEO-only, 10 seconds; AUDIO-only, 20 seconds, mono 16 kHz. Their original source intervals, hashes, and CC BY 3.0 attribution are in [`review_manifest.json`](../../review/bridge_f10_examples/review_manifest.json). The audio clip is from the real film and spans a music-to-dialogue scene change. A separate hard splice between unrelated music recordings was tested earlier; it is excluded from this review packet because it is not a natural transition.

## Findings against the current priorities

### Semantic matcher

Positive-only scene alternatives yield an accepted dialogue scene in three adjacent windows of the real clip, while the first music window remains uncertain. In the separate 65-second instrumental probe, all 13/13 broad music-scene windows remained uncertain (top-candidate cosine min/mean/max 0.718/0.744/0.766; margin 0.0004/0.0143/0.0233). Do not lower the 0.6 similarity or 0.05 margin thresholds from these label-free probes. The per-axis text hypotheses and raw scores are in the linked CSVs below.

The X-CLIP sequence scan is also a negative diagnostic: the action label `rises_from_bed_to_standing` stays top after the visible rise, its logit increases while average pixel change falls, and a later isolated frame-change spike does not alter the label. Pixel deltas can reflect camera movement, scene cuts, or object motion, so they are diagnostic only. Do not use X-CLIP margin/logit or pixel delta as confidence gates. A temporal action model and independent labels are still required before B0 can accept this visual event.

### Music development

For the music-to-dialogue excerpt, L2 abstains from publishing instrument/vocal/tempo details while the music premise is unsupported. The broader instrumental probe also failed to identify its source change reliably: at the 50000 ms synthetic splice, the candidate changed to `piano_timbre`, but all instrument-family decisions were uncertain; even windows from the choir-and-organ recording continued to favor piano. The embedding-distance novelty peak at that splice was not unique to it. These results do not support a natural music-layer transition detector yet.

### CPU realtime

The existing cold-cache 60-second Qwen live run remains below 1x: capture 41.818 seconds, embeddings 35.099 seconds of coverage, 548 shared-prefetch drops, two pre-stop Qwen captions with 20.758-second median observed lag, and 3.432 GB peak process-tree RSS. See [F10.02 live follow-up](f10_02_followup_20261027.md). Offline clip timings above must not be read as realtime performance.

## Human verification and training gate

The review packet contains no labels or answer key. Independent labels are still **0** for this packet. Review blind using [`review_guide.md`](../../review/bridge_f10_examples/review_guide.md), fill [`human_labels_template.csv`](../../review/bridge_f10_examples/human_labels_template.csv), then run [`validate_f10_review_labels.py`](../../../scripts/validate_f10_review_labels.py). After validation, [`build_f10_reviewed_graphs.py`](../../../scripts/build_f10_reviewed_graphs.py) builds separate EventGraph/Qwen-request bundles from those human labels. Its mapping was smoke-tested with synthetic review rows against the real serialized VIDEO frame sequence; those synthetic rows were not saved as labels. Until a completed review arrives, the X-CLIP action and music-to-dialogue boundary remain model candidates, not verified ground truth. The B1 training decision remains **NO-GO**: there are no rights-cleared source-separated train/validation/held-out groups, no independent four-mode evaluation, and no bounded GPU budget.

## Reproduction

```powershell
# Audio-only extraction: source movie time 185–205 s (the fixture begins at source time 120 s)
ffmpeg.exe -y -ss 65 -i benchmarks/fixtures/real_poc/tears_of_steel_120_210s.mp4 -t 20 -vn -ac 1 -ar 16000 -c:a pcm_s16le benchmarks/review/bridge_f10_examples/audio_only_tos_185-205s.wav

# Re-run the audio-only L1/L2/L3 analysis and positive-only probes
.venv/Scripts/shsd.exe analyze benchmarks/review/bridge_f10_examples/audio_only_tos_185-205s.wav --levels L1,L2,L3 --cpu-only --offline --threads 4 --window-seconds 5 --narrator-mode qwen --output benchmarks/reports/bridge_f10/music_transition_real_video_20261027/audio_only_analysis.jsonl
.venv/Scripts/python.exe scripts/probe_music_multiclass.py --source benchmarks/review/bridge_f10_examples/audio_only_tos_185-205s.wav --threads 4 --output-dir benchmarks/reports/bridge_f10/music_transition_real_video_20261027/multiclass
.venv/Scripts/python.exe scripts/probe_music_dynamics.py --source benchmarks/review/bridge_f10_examples/audio_only_tos_185-205s.wav --threads 4 --output-dir benchmarks/reports/bridge_f10/music_transition_real_video_20261027/dynamics

# Re-run the external VIDEO-only action candidate (pinned MIT X-CLIP snapshot must be in the local ignored model cache)
.venv/Scripts/python.exe scripts/probe_video_action_xclip.py --video benchmarks/fixtures/real_poc/tears_of_steel_120_140s.mp4 --start-ms 1000 --end-ms 9000 --source-pts-offset-ms 120000 --threads 4 --report benchmarks/reports/bridge_f10/video_action_hypothesis_xclip_tears120-140.json
.venv/Scripts/python.exe scripts/probe_video_action_xclip.py --video benchmarks/fixtures/real_poc/tears_of_steel_120_140s.mp4 --start-ms 0 --end-ms 20000 --scan-window-ms 8000 --scan-stride-ms 1000 --source-pts-offset-ms 120000 --stream-id f10-video-only-tears120-140-sequence --threads 4 --report benchmarks/reports/bridge_f10/video_action_sequence_xclip_tears120-140.json
```

Model: `microsoft/xclip-base-patch32`, MIT, revision `a2e27a78a2b5d802e894b8a1ef14f3a8ce490963`. X-CLIP is an external diagnostic only; weights are not committed or integrated into the default application path.

## Raw outputs

- [`video_action_hypothesis_xclip_tears120-140.json`](video_action_hypothesis_xclip_tears120-140.json)
- [`video_action_sequence_xclip_tears120-140.json`](video_action_sequence_xclip_tears120-140.json)
- [`audio_only_analysis.jsonl`](music_transition_real_video_20261027/audio_only_analysis.jsonl)
- [`multiclass summary`](music_transition_real_video_20261027/multiclass/music_multiclass_probe.json) and [scores](music_transition_real_video_20261027/multiclass/music_multiclass_scores.csv)
- [`music-dynamics summary`](music_transition_real_video_20261027/dynamics/music_dynamics_probe.json) and [per-window scores](music_transition_real_video_20261027/dynamics/music_dynamics_prompt_scores.csv)
- [Earlier synthetic splice diagnostic](music_transition_probe_20261027/dynamics/music_dynamics_probe.json)
