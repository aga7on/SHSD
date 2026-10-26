# Compact vision profile A/B ? 2026-10-26

## Change

`shsd analyze --vision-profile compact` and API `vision_profile: "compact"` now encode sampled frames with EmbeddingGemma 2 image `max_soft_tokens=140` (default `standard` remains 280). The selected value is included in analysis/session metadata. Compact-frame cache identities and `input_preprocess_version` are distinct from standard embeddings. The processor default and existing standard cache keys remain unchanged.

The 70-token mode is not exposed: it changed text-prompt rankings in both microbenchmark frames. This is an opt-in CPU throughput profile, not a quality-equivalent replacement for standard.

## Direct inference microbenchmark

Pinned revision `914f7f89142e33e77833254d9c9b90c3cef7303b`, CPU, 4 threads, 320x180 local synthetic fixture frames, two calls per setting. Each call processed one frame.

| Image soft tokens | Mean latency, green scene | Mean latency, moving pattern | Cosine to 280, green / motion | Six-prompt ranking |
| ---: | ---: | ---: | ---: | --- |
| 280 | 4,043 ms | 4,002 ms | 1.000 / 1.000 | baseline |
| 140 | 1,313 ms | 1,296 ms | 0.9861 / 0.9867 | same on both frames |
| 70 | 512 ms | 509 ms | 0.9810 / 0.9679 | changed on both frames |

The prompt rankings use synthetic labels and a small fixed prompt list; they are a regression signal, not a visual-recognition accuracy measure.

## Full analyzer A/B

Ran `video_scene_cuts_8s.mp4` at 4 threads with L0/L1, isolated caches, and template narration. Raw timelines: [`standard.jsonl`](vision_profile_ab_20261026/standard.jsonl) and [`compact.jsonl`](vision_profile_ab_20261026/compact.jsonl).

| Profile | Image inference time | Total elapsed | L0 scene-cut events | L1 window matches |
| --- | ---: | ---: | ---: | --- |
| standard, 280 | 4,313.8 ms | 17.525 s | 3 | 4, all uncertain |
| compact, 140 | 1,389.4 ms | 14.656 s | 3, same intervals | 4, all uncertain |

Each run emitted one visual embedding; later work was explicitly skipped under `runtime_backpressure`. Both runs reached final C/E/D/R=8,000 ms. The four L1 matches came from that one embedding. Three L0 scene-cut events were identical. One uncertain L1 top label changed from `unknown` to `natural_scene`; no semantic claim was accepted. The measured 3.1x reduction is per visual inference; model and text-profile initialization dominated end-to-end runtime, which improved by 16.4% on this short clip.

## Additional fix encountered during the run

The first video-only run exposed stale coverage revisions when overlapping frame windows updated inactive L2/L3 coverage. Draft and terminal coverage writes now use `mark_revisioned()`. Re-running the same analyzer fixture in both profiles completed without the exception and reported explicit backpressure coverage.

## Reproduction

From the repository root:

```powershell
shsd analyze tests/fixtures/media/video_scene_cuts_8s.mp4 --cpu-only --levels L0,L1 --threads 4 --narrator-mode template --vision-profile standard --cache-dir runs/vision-standard --output runs/vision-standard.jsonl
shsd analyze tests/fixtures/media/video_scene_cuts_8s.mp4 --cpu-only --levels L0,L1 --threads 4 --narrator-mode template --vision-profile compact --cache-dir runs/vision-compact --output runs/vision-compact.jsonl
```

## Live 2x/5x follow-up

The compact setting was also used in a 60-second-per-scale loopback RTSP soak. At 2x it reduced shared-prefetch drops from 1,618 to 503 and scheduler pressure rejects from 35 to zero versus the earlier standard-profile run. At 5x it did not improve overload: 5,918 drops and 28 rejects, with up to 40.1 seconds of observed positive C?R[L1] lag. Final watermarks aligned after shutdown and drain, which does not establish realtime processing. See [`live_rtsp_vision_compact_60s_20261026.md`](live_rtsp_vision_compact_60s_20261026.md) and its raw report.

## Decision and limits

Keep `standard` as the default and offer `compact` for callers that prefer lower visual inference time. The 140-token setting preserved the tiny microbenchmark's prompt ranking, but it changed one uncertain analyzer label. This synthetic clip does not establish natural-scene recall, precision, or camera behavior. The 2x/5x live acceptance item remains open.
