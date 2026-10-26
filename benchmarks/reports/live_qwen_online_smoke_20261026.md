# Live Qwen L2/L3 online smoke

**Input:** 90-second *Tears of Steel* A/V excerpt, published through local RTSP at real-time speed. The publisher was stopped after 35 seconds. Analysis used CPU, 4 threads, 5-second windows, and levels L0/L1/L2/L3 with the Qwen narrator.

## Result

L2 event revisions and Qwen captions were emitted while the RTSP publisher was still running:

- Before stop: 5 L1 events, 3 L2 events, and 2 Qwen captions were visible.
- The first caption appeared 25.877 seconds after publisher start, 9.123 seconds before stop.
- The pre-stop snapshot at 34.832 seconds had `C=10.117 s`, `E=10.034 s`, `R[L1]=15.110 s`, `R[L2]=5.110 s`, and `R[L3]=5.110 s`. L2/L3 lag behind L1 is expected while events wait for stability and Qwen work drains.
- After stop, final `C/E/R[L1]/R[L2]/R[L3]` reached 18.244 seconds of captured source; post-stop drain took 0.659 seconds.
- The three live L2 event outputs were about 16.85–16.88 seconds behind their source end timestamps. This run therefore verifies online publication, but does not establish real-time throughput.

## Output quality

Both Qwen captions were generated from L0 scene-cut evidence and repeated the generic text `Обнаружено заметное изменение изображения.` No useful music or dialogue description was produced. The audio L1 music-presence event remained `uncertain`: best cosine 0.736, margin 0.009. This is consistent with the separately measured near-tie between music-present and music-absent text candidates; the threshold was not changed.

The API's manual L3 `/refine` request returned HTTP 409 while the stream was running. Captions in this run came from the new automatic online L2→L3 path.

## Artifacts

- `live_qwen_online_smoke_20261026/report.json` — timings, pre-stop and terminal watermarks, output counts, and captions.
- `live_qwen_online_smoke_20261026/events_live.json` — event revisions.
- `live_qwen_online_smoke_20261026/captions_live.json` — generated captions.
- `live_qwen_online_smoke_20261026/api.log` — API request trace.
