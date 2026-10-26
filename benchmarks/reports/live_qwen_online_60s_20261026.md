# 60-second live CPU + Qwen latency check

## Setup

The 90-second *Tears of Steel* A/V excerpt was published through local RTSP with FFmpeg `-re` for 60.0 seconds. SHSD ran on CPU with four inference threads, five-second windows, standard vision sampling, L0/L1/L2/L3, and Qwen requested for L3. The host CPU was AMD Ryzen 9 9900X3D (12 cores / 24 logical CPUs). MediaMTX v1.21.2 was downloaded from the [official release](https://github.com/bluenviron/mediamtx/releases/tag/v1.21.2); the archive SHA-256 was verified as `a84224f5a490855684e62ba6fb71e80ea2a5e16aed61883bb58380290e93e467`.

Three runs used the same source and publisher duration: a cold four-thread run, a warm four-thread run, and a warm twelve-thread run reusing the warm embedding cache. Qwen remained enabled in all runs. Only outputs first observed while the publisher was running count as live. Event output lag uses event revision time minus source end time. Caption output lag uses the first 1-second API polling snapshot where the caption appeared, so it is an upper-bound estimate with up to one second of polling delay.

## Pre-stop progress and output lag

| Measure | Cold cache, 4 threads | Warm cache, 4 threads | Warm cache, 12 threads |
|---|---:|---:|---:|
| Publisher duration | 60.000 s | 60.000 s | 60.000 s |
| Last sampled capture C | 42.012 s | 43.015 s | 42.997 s |
| Last sampled embedding E | 35.075 s | 40.015 s | 40.004 s |
| Last sampled R[L1] | 35.075 s | 40.061 s | 43.003 s |
| Last sampled R[L2] | 25.075 s | 25.061 s | 35.628 s |
| Last sampled R[L3] | 29.887 s | 25.061 s | 35.118 s |
| Live L1 event revisions | 26 | 30 | 35 |
| L1 output lag p50 / p95 / max | 21.145 / 30.942 / 30.947 s | 16.538 / 25.899 / 30.769 s | 18.798 / 28.517 / 28.529 s |
| Live L2 event revisions | 12 | 15 | 15 |
| L2 output lag p50 / p95 / max | 16.572 / 16.580 / 16.580 s | 16.181 / 30.770 / 30.770 s | 16.833 / 16.841 / 16.841 s |
| Live L3 captions | 2 | 4 | 7 |
| L3 first-observed lag p50 / p95 / max | 20.126 / 20.649 / 20.649 s | 19.014 / 19.323 / 19.323 s | 19.064 / 19.705 / 19.705 s |
| Post-stop wait to terminal state | 19.879 s | 19.776 s | 15.993 s |

The first live caption appeared at 26.489 s in the cold four-thread run, 26.479 s in the warm four-thread run, and 25.692 s in the warm twelve-thread run. The cold run's two live captions were one Qwen generation and one fallback. The four- and twelve-thread warm runs produced four and seven live Qwen captions respectively; the generated text repeats a generic scene-change description. Nine additional captions in each warm run arrived only after the publisher stopped and are excluded from L3 live latency.

## Stop and final capture

All publishers stopped at 60.0 seconds. Terminal analysis state arrived 79.879 seconds after start in the cold run, 79.776 seconds in the warm four-thread run, and 75.993 seconds in the warm twelve-thread run. Final capture C reached only 43.509 s, 43.865 s, and 43.276 s respectively; the remainder of the 60-second publisher interval had not been ingested. Post-stop drain completed analysis of captured media, but it does not count as live throughput.

## Result

The CPU/Qwen pipeline emitted L1, L2, and L3 output before stop, but did not sustain real-time source coverage: capture reached about 43 seconds during a 60-second publication at both four and twelve threads. Twelve threads advanced pre-stop R[L2] from 25.1 s to 35.6 s and reduced post-stop wait to 16.0 s, while final capture remained 43.3 s. L1 output lag p50 was 16.5–21.1 s at four threads and 18.8 s at twelve threads; L2 lag p50 was 16.2–16.8 s. L3 caption lag p50 stayed about 19 s. Qwen's generated text remained generic and did not describe the dialogue or music. Increasing inference threads alone does not fix capture throughput. This one-times loopback test does not close F6.01; sustained 2x/5x acceptance and physical-camera validation remain open.

## Raw evidence

- Cold cache: `live_qwen_online_60s_20261026/report.json`, `events_live.json`, `captions_live.json`.
- Warm embedding cache: `live_qwen_online_60s_cache_recheck_20261026/report.json`, `events_live.json`, `captions_live.json`.
- Warm embedding cache, twelve threads: `live_qwen_online_60s_threads12_20261026/report.json`, `events_live.json`, `captions_live.json`.
- Runner: `scripts/benchmark_live_qwen.py`.
