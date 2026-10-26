# Shared embedding dispatcher: 25-second RTSP check

Date: 2026-10-26. The API now routes media embedding jobs from streams that share a pooled provider through one bounded round-robin dispatcher. Each analyzer still applies results on its own consumer thread. The dispatcher permits 64 pending jobs, retains at most 256 source summaries, and reports per-source queue wait and inference totals.

## Configuration

- AMD Ryzen 9 9900X3D, 12 cores / 24 logical CPUs; Python 3.14.6.
- Four inference threads per provider, compact vision profile, 4 GiB runtime pressure threshold.
- Synthetic local RTSP audio/video; two sources at 2x and five at 5x; fresh cache for each scenario.
- After every source first reported capture progress, the runner observed the scenario for 25 seconds and then requested stop.

## Results

| Scale | Dispatcher | Capture ready | Wait to capture ready | Scenario wall time | Shared prefetch drops | Semantic rejects | Peak process-tree RSS | Per-stream elapsed / captured-media ratio |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2x | Before | yes | 31.52 s | 58.66 s | 427 | 0 | 2.35 GiB | 1.63–1.64 |
| 2x | Round-robin | yes | 31.68 s | 58.44 s | 252 | 0 | 2.31 GiB | 1.63–1.65 |
| 5x | Before | no | 127.21 s timeout | 140.76 s | 8,612 | 37 | 2.41 GiB | 1.12–1.20* |
| 5x | Round-robin | yes | 12.84 s | 47.21 s | 3,083 | 32 | 2.33 GiB | 1.17–1.34 |

At 5x, all five sources now reached capture progress and stopped in a terminal state. The new run dispatched 1–3 embedding jobs per source during the observed interval. In the preceding run, concurrent provider calls spent 623.1 seconds in worker execution for 14 completed jobs, including 492.9 seconds beyond recorded model inference. With one dispatcher, nine completed jobs used 36.4 seconds of worker execution for 36.2 seconds of model inference; queue waiting is reported separately. This removes the very long provider-lock stragglers seen in the earlier trace.

The table's total drops and wall times are not a direct throughput A/B: the preceding 5x run never became capture-ready and ran until its 120-second capture timeout, while the new run proceeded to the 25-second observation after 12.84 seconds. The per-stream elapsed/media ratio also remains above 1 at 5x, and the 2x ratio is about 1.64 in this short cold-cache run. This is evidence that dispatch is fairer and bounded under loopback load, not that sustained real-time processing has been achieved. Physical-camera input was not tested.

Raw runner output, including per-stream watermarks and dispatcher counters: [`report.json`](report.json). The preceding no-shared-dispatcher diagnostic is [`live_rtsp_modality_recheck_20261026/report.json`](../live_rtsp_modality_recheck_20261026/report.json).
