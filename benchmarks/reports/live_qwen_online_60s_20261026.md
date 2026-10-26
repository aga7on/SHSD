# 60-second live CPU + Qwen latency check

## Setup

The 90-second *Tears of Steel* A/V excerpt was published through local RTSP with FFmpeg `-re` for 60.0 seconds. SHSD ran on CPU with four inference threads, five-second windows, standard vision sampling, L0/L1/L2/L3, and Qwen requested for L3. The host CPU was AMD Ryzen 9 9900X3D (12 cores / 24 logical CPUs). MediaMTX v1.21.2 was downloaded from the [official release](https://github.com/bluenviron/mediamtx/releases/tag/v1.21.2); the archive SHA-256 was verified as `a84224f5a490855684e62ba6fb71e80ea2a5e16aed61883bb58380290e93e467`.

Four runs used the same source and 60-second publisher duration: cold and warm four-thread runs with Qwen L3, a warm twelve-thread Qwen run, and a warm twelve-thread control with L3/Qwen disabled. The control reuses the warm embedding cache. Only outputs first observed while the publisher was running count as live. Event output lag uses event revision time minus source end time. Caption output lag uses the first 1-second API polling snapshot where the caption appeared, so it is an upper-bound estimate with up to one second of polling delay.

## Pre-stop progress and output lag

| Measure | Cold cache, 4 threads | Warm cache, 4 threads | Warm cache, 12 threads | No L3/Qwen, 12 threads |
| --- | ---: | ---: | ---: | ---: |
| Publisher duration | 60.000 s | 60.000 s | 60.000 s | 60.000 s |
| Last sampled capture C | 42.012 s | 43.015 s | 42.997 s | 42.022 s |
| Last sampled embedding E | 35.075 s | 40.015 s | 40.004 s | 40.023 s |
| Last sampled R[L1] | 35.075 s | 40.061 s | 43.003 s | 42.022 s |
| Last sampled R[L2] | 25.075 s | 25.061 s | 35.628 s | 35.093 s |
| Last sampled R[L3] | 29.887 s | 25.061 s | 35.118 s | disabled |
| Live L1 event revisions | 26 | 30 | 35 | 35 |
| L1 output lag p50 / p95 / max | 21.145 / 30.942 / 30.947 s | 16.538 / 25.899 / 30.769 s | 18.798 / 28.517 / 28.529 s | 17.991 / 24.791 / 29.407 s |
| Live L2 event revisions | 12 | 15 | 15 | 20 |
| L2 output lag p50 / p95 / max | 16.572 / 16.580 / 16.580 s | 16.181 / 30.770 / 30.770 s | 16.833 / 16.841 / 16.841 s | 17.640 / 24.791 / 24.793 s |
| Live L3 captions | 2 | 4 | 7 | 0 |
| L3 first-observed lag p50 / p95 / max | 20.126 / 20.649 / 20.649 s | 19.014 / 19.323 / 19.323 s | 19.064 / 19.705 / 19.705 s | disabled |
| Post-stop wait to terminal state | 19.879 s | 19.776 s | 15.993 s | 1.168 s |

## Runtime cost and no-L3 control

| Runtime metric | Warm Qwen, 12 threads | No L3/Qwen, 12 threads |
|---|---:|---:|
| End-to-end elapsed | 74.639 s | 59.735 s |
| Peak process-tree RSS | 3.263 GiB | 2.333 GiB |
| Media-ingest packets / dropped | 2,894 / 0 | 2,838 / 0 |
| Shared-prefetch drops | 188 | 145 |
| Embedding inference, audio / image | 2.656 / 7.219 s | 2.408 / 7.127 s |
| Qwen calls / fallback captions | 16 / 9 | 0 / 0 |

With L3 disabled, live capture C was 42.022 s versus 42.997 s with Qwen, and R[L2] was 35.093 s versus 35.628 s. These are close; the run does not support Qwen as the cause of the capture shortfall. Disabling L3 reduced terminal wait by 14.825 s and peak process-tree RSS by about 0.930 GiB. Both runs had zero decoder-ingest drops. The remaining capture gap should be traced through decode, shared media dispatch, and capture-watermark accounting.

The first live caption appeared at 26.489 s in the cold four-thread run, 26.479 s in the warm four-thread run, and 25.692 s in the warm twelve-thread run. The cold run's two live captions were one Qwen generation and one fallback. The four- and twelve-thread warm runs produced four and seven live Qwen captions respectively; the generated text repeats a generic scene-change description. Nine additional captions in each warm run arrived only after the publisher stopped and are excluded from L3 live latency.

## Stop and final capture

All publishers stopped at 60.0 seconds. Terminal analysis state arrived 79.879 seconds after start in the cold run, 79.776 seconds in the warm four-thread run, and 75.993 seconds in the warm twelve-thread run. Final capture C reached only 43.509 s, 43.865 s, and 43.276 s respectively; the remainder of the 60-second publisher interval had not been ingested. Post-stop drain completed analysis of captured media, but it does not count as live throughput.

## Result

The Qwen pipeline emitted L1, L2, and L3 output before stop but did not sustain real-time source coverage: capture reached about 43 seconds during a 60-second publication at both four and twelve threads. A warm twelve-thread control with L3/Qwen disabled captured 42.0 seconds, reached R[L2]=35.1 seconds, and stopped draining in 1.2 seconds. Qwen therefore accounts for meaningful memory use and post-stop delay, while the measured capture shortfall remains upstream of narration. L1/L2 output lag p50 was 16.5–21.1 seconds at four threads and 18.8 seconds at twelve threads with Qwen; the no-L3 control measured 18.0/17.6 seconds. L3 caption lag p50 stayed about 19 seconds. Qwen text remained generic and did not describe the dialogue or music. This one-times loopback test does not close F6.01; sustained 2x/5x acceptance and physical-camera validation remain open.

## Raw evidence

- Cold cache: `live_qwen_online_60s_20261026/report.json`, `events_live.json`, `captions_live.json`.
- Warm embedding cache: `live_qwen_online_60s_cache_recheck_20261026/report.json`, `events_live.json`, `captions_live.json`.
- Warm embedding cache, twelve threads: `live_qwen_online_60s_threads12_20261026/report.json`, `events_live.json`, `captions_live.json`.
- Runner: `scripts/benchmark_live_qwen.py`.
- Warm twelve-thread control with L3/Qwen disabled: `live_no_l3_60s_threads12_20261026/report.json`, `events_live.json`, `captions_live.json`.
