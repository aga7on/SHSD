# Live RTSP thread sweep: 4, 8, and 12 threads

Date: 2026-10-26. This comparison uses three isolated 60-second synthetic RTSP runs with compact vision, a fresh embedding cache per run, and a 4 GiB memory threshold. Each run exercised 2x and 5x concurrent sources on the local Ryzen 9 9900X3D. Every scenario reached capture-ready and every stream reached terminal `stopped`.

RTF is the stream's `end_to_end_elapsed` divided by its captured media duration. Peak L1 lag is the largest pre-stop timeline sample. Final L1 issue spans sum `R/L1` gap and skipped intervals; the intervals remain visible in the final coverage report even when the watermark reaches the source end after shutdown.

## Results

| Scale | Threads | RTF median / max | Peak observed L1 lag | Shared prefetch drops | Semantic pressure rejects | Final R/L1 issue spans | Peak process-tree RSS |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2x | 4 | 1.319 / 1.322 | 6.9 s | 487 | 1 | 6.5 / 138.6 s (4.7%) | 2.31 GiB |
| 2x | 8 | 1.246 / 1.250 | 5.0 s | 36 | 0 | 8.3 / 139.3 s (6.0%) | 2.32 GiB |
| 2x | 12 | 1.311 / 1.313 | 5.0 s | 151 | 0 | 1.2 / 132.1 s (0.9%) | 2.32 GiB |
| 5x | 4 | 1.186 / 1.231 | 41.3 s | 6,074 | 37 | 297.7 / 347.6 s (85.6%) | 2.33 GiB |
| 5x | 8 | 1.158 / 1.172 | 51.9 s | 7,202 | 81 | 196.4 / 345.6 s (56.8%) | 2.35 GiB |
| 5x | 12 | 1.108 / 1.158 | 48.6 s | 6,864 | 47 | 274.7 / 343.9 s (79.9%) | 2.35 GiB |

## Interpretation

At 5x, 12 threads had the lowest median RTF, while 8 threads had the fewest final R/L1 issue spans. Both higher-thread runs increased prefetch drops and scheduler pressure rejects relative to four threads; eight threads also had the highest observed lag. All three profiles remained above RTF 1 at 5x, and all retained substantial L1 gaps/skips. The sweep therefore does not establish sustained real-time processing or a generally better thread default. Keep the four-thread default and retain the measured tradeoffs for future target-specific tuning.

The 2x results also remained above RTF 1 in this cold-cache live benchmark. This is synthetic loopback evidence, not physical-camera acceptance. The physical camera was not available during the run.

## Artifacts

- Four threads: [`live_rtsp_shared_dispatch_60s_20261026/report.json`](live_rtsp_shared_dispatch_60s_20261026/report.json)
- Eight threads: [`live_rtsp_shared_dispatch_threads8_60s_20261026/report.json`](live_rtsp_shared_dispatch_threads8_60s_20261026/report.json)
- Twelve threads: [`live_rtsp_shared_dispatch_threads12_60s_20261026/report.json`](live_rtsp_shared_dispatch_threads12_60s_20261026/report.json)
- Earlier summary and 25-second controls: [`embedding_thread_scale_live_20261026.md`](embedding_thread_scale_live_20261026.md)
