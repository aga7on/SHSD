# Shared embedding dispatcher: 60-second RTSP soak

Date: 2026-10-26. This follow-up repeats the compact-vision loopback run for 60 seconds after every source reports capture progress. It uses the round-robin per-provider inference queue, bounded to 64 pending jobs and 256 retained source summaries, and compares with the prior 60-second compact run, which used per-stream workers.

## Configuration

- AMD Ryzen 9 9900X3D, 12 cores / 24 logical CPUs; Python 3.14.6.
- Four inference threads per provider, compact vision profile, 4 GiB runtime pressure threshold.
- Synthetic local RTSP audio/video, fresh cache for each scenario, two sources at 2x and five at 5x.
- All sources reached capture progress; each scenario then ran for 60 seconds before cooperative stop.

## Results

| Scale | Dispatcher | Capture-ready wait | Scenario wall time | Shared prefetch drops | Semantic rejects | Max observed L1 lag | Peak process-tree RSS | Per-stream elapsed / captured-media ratio |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2x | Per-stream | 31.22 s | 91.75 s | 503 | 0 | 8.14 s | 2.35 GiB | 1.31 |
| 2x | Round-robin | 31.65 s | 92.48 s | 487 | 1 | 6.92 s | 2.31 GiB | 1.32 |
| 5x | Per-stream | 13.34 s | 80.78 s | 5,918 | 28 | 40.06 s | 2.37 GiB | 1.08–1.15 |
| 5x | Round-robin | 13.39 s | 86.94 s | 6,074 | 37 | 41.34 s | 2.33 GiB | 1.14–1.23 |

All seven streams reached terminal `stopped`. The dispatcher removes provider-lock waiting from worker execution: at 5x, worker execution fell from 333.4 seconds across eight jobs to 77.1 seconds across ten jobs, while recorded model inference was 70.3 and 76.5 seconds respectively. In the new run, one audio job still took 41.4 seconds of inference. That job cost and shared queue waiting remain visible as source lag.

The 60-second soak shows no sustained-throughput gain from fairness alone. At 5x, pre-stop L1 lag remained about 40–41 seconds, RTF stayed above 1, and drops/rejects were slightly higher than the preceding compact run. The dispatcher improves bounded service and removes lock stragglers; it does not make this CPU configuration real-time. Physical-camera behavior remains unverified.

Raw runner output with source timelines and per-source dispatcher counters: [`report.json`](report.json). Previous compact soak: [`live_rtsp_vision_compact_60s_20261026/report.json`](../live_rtsp_vision_compact_60s_20261026/report.json).
