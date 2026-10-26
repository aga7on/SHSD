# F10.02 initial B0 and CPU audit

Date: 2026-10-27 · local Windows CPU · EmbeddingGemma 2 `914f7f89142e33e77833254d9c9b90c3cef7303b` · Qwen3-0.6B GGUF `13ac06624948e4d8589cb4b6f90100837342fcb8`.

## VIDEO-only: `Tears of Steel`, source 02:00–02:20

Input: the locally available, CC BY 3.0 excerpt documented in [`real_poc/README.md`](../fixtures/real_poc/README.md), source SHA-256 `014324f1575464b248acff73c858dec66059b9afb271875dd0c82d5460b7d588`. A silent derivative was made with `ffmpeg -i tears_of_steel_120_140s.mp4 -an -c:v copy`; it preserves the clip's frame timestamps relative to the 02:00:00 excerpt. Map clip PTS to the original source with `source_pts_ms = clip_pts_ms + 120000`.

Reproduction from the repository root, when the local fixture is present:

```powershell
ffmpeg -hide_banner -loglevel error -y -i benchmarks/fixtures/real_poc/tears_of_steel_120_140s.mp4 -an -c:v copy benchmarks/reports/bridge_f10/tears_steel_120_140s_video_only.mp4
python -c "from shsd.cli import main; raise SystemExit(main())" analyze benchmarks/reports/bridge_f10/tears_steel_120_140s_video_only.mp4 --levels L0,L1,L2,L3 --cpu-only --offline --threads 4 --window-seconds 2 --stream-id f10-video-only-tears120-140 --event-db ':memory:' --cache-dir .cache --output benchmarks/reports/bridge_f10/video_only_tears120-140.jsonl
python scripts/probe_video_action_similarity.py benchmarks/reports/bridge_f10/tears_steel_120_140s_video_only.mp4 --start-ms 0 --end-ms 8000 --threads 4 --report benchmarks/reports/bridge_f10/video_action_similarity_probe_0_8s.json
python scripts/probe_video_action_similarity.py benchmarks/reports/bridge_f10/tears_steel_120_140s_video_only.mp4 --start-ms 8000 --end-ms 20000 --threads 4 --report benchmarks/reports/bridge_f10/video_action_similarity_probe_8_20s.json
```

The independent visual review of frames at 2-second intervals supports this **provisional** event candidate: `man_1 → rises from bed to standing → bed_1`, source interval 02:00:00–02:00:08, evidence PTS 120000, 122000, 124000, 126000, and 128000 ms. This is an agent visual review, not a second human's verification, and is not eligible as a training label until a human reviewer confirms it.

The production output did not detect that action. It produced 24/24 uncertain visual L1 matches, 12 graph nodes, 11 start-order edges, and the single Qwen caption `Обнаружено заметное изменение изображения.` No entity-action-object claim was emitted. The `person_visible` candidate scored 0.6340 with margin 0.0388 against the configured 0.05 margin. Eight L0 `scene_cut` events were emitted; several are 1-second-spaced inside the same apparent camera setup, so motion may be confused with cuts.

The separate native VIDEO/text diagnostic is not a published classifier: for 0–8s, `sitting_up_from_bed` scored 0.6884, `reaching_toward_candle` 0.6776, and `lying_on_bed` 0.6760. For 8–20s, `sitting_up_from_bed` scored 0.6965, `reaching_toward_candle` 0.6835, and `getting_out_of_bed` 0.6784. The top-vs-runner-up margins (0.0108 and 0.0130) do not support a confident action event, and the top concept did not change across the two intervals. These are raw cosine similarities, not probabilities or verified labels.

The run took 33.29s for 20s of video (RTF 1.66, including startup and candidate encoding), with 16.81s embedding inference, 12.50s profile candidate encoding, 21ms L1 matching, 121ms L2 refinement, 3.45s L3 narration, and 2.69GB peak process-tree RSS. Two of six image embeddings were cache hits. This is an offline file pass, not a live latency result.

The two similarity probe JSONs are checked in beside this report. The full analyzer JSONL remains in the local ignored benchmark output; rerun the command above to reproduce it.

## AUDIO-only: same source interval

The AAC track was extracted to mono PCM at 48kHz and analyzed with the same model revisions and L0/L1/L2/L3 levels. Reproduction:

```powershell
ffmpeg -hide_banner -loglevel error -y -i benchmarks/fixtures/real_poc/tears_of_steel_120_140s.mp4 -vn -ac 1 -ar 48000 -c:a pcm_s16le benchmarks/reports/bridge_f10/tears_steel_120_140s_audio_only.wav
python -c "from shsd.cli import main; raise SystemExit(main())" analyze benchmarks/reports/bridge_f10/tears_steel_120_140s_audio_only.wav --levels L0,L1,L2,L3 --cpu-only --offline --threads 4 --window-seconds 5 --stream-id f10-audio-only-tears120-140 --event-db ':memory:' --cache-dir .cache --output benchmarks/reports/bridge_f10/audio_only_tears120-140.jsonl
```

All 16 audio L1 matches were uncertain. `music_presence` selected `environment_dominant` for 0–10s (cosine about 0.755, margin 0.006/0.001) and `conversation_dominant` for 10–20s (cosine about 0.745/0.751, margins 0.039/0.049). No music layer or musical transition was confirmed; L3 was skipped because no claim passed its gate. This interval is therefore **not** the requested positive music-transition example. Keep the label unknown pending a suitable independently reviewed audio source.

End-to-end offline time was 17.16s for 20.02s audio, including 15.31s profile candidate encoding; audio embedding inference was 1.53s, L1 14ms, L2 120ms, L3 0.4ms (skipped), and peak process-tree RSS 1.94GB. A sub-1 RTF here does not prove live stream stability.

The full analyzer JSONL remains in the local ignored benchmark output; rerun the command above to reproduce it.

## Qwen during a live stream

The existing 85-second CPU RTSP run used the real 90-second *Tears of Steel* excerpt with L0/L1/L2/L3 and Qwen requested. At publisher stop, capture had reached 68.067s, embeddings 60.068s, L1 65.067s, while L2 and L3 cursors were each only 93ms. There were zero captions before stop; `/refine` returned HTTP 409 (`refine is available after the file analysis has completed`). The first Qwen caption arrived 4.154s after stop, after draining; 17 captions were eventually emitted. Thus this run confirms that Qwen L3 is not presently measured online. Post-stop Qwen latency must not be counted as live L3 performance.

Raw source evidence is the existing local [`live_qwen_real_tears_20261026/report.json`](../live_qwen_real_tears_20261026/report.json) and `report_live_qwen.md`; those files are local benchmark outputs. No online L2/L3 p50/p95 can be reported from this run.

## Decision and remaining work

- Do not lower matcher thresholds: visual and audio candidates have small margins against plausible competitors.
- B0 is **not ready for bridge training**: its graph still contains pooled-embedding claims and signal-level scene cuts, not verified action/object nodes. `AVFeatureBatch` preserves PTS in isolation but is not connected to the default `analyze`/Qwen path.
- The visual action candidate needs independent human confirmation; the audio-only transition example still needs an appropriate source and independently reviewed timestamps.
- P1 CPU work remains open: progressive online L2/L3 must run during capture before a valid Qwen-enabled live latency measurement is possible. Keep B1 training **NO-GO**.
