# CPU thread scaling with shared live inference

Date: 2026-10-26. This report combines a local EmbeddingGemma thread microbenchmark with compact-vision RTSP checks using the shared per-provider round-robin dispatcher. The live tests measure end-to-end tradeoffs that are absent from isolated model calls.

## Host and local model timing

- AMD Ryzen 9 9900X3D, 12 physical / 24 logical CPUs, Python 3.14.6.
- `scripts/benchmark_cpu.py --threads 4 6 8 12 --workers 1 --repeats 2 --offline`.
- Two cache-miss samples per stage/thread count; p50 latency is small-sample evidence.

| Threads | 5 s audio p50 | 10 s audio p50 | Frame p50 | 8 s video p50 | Joint A/V p50 |
|---:|---:|---:|---:|---:|---:|
| 4 | 257 ms | 471 ms | 4.04 s | 12.64 s | 9.91 s |
| 6 | 244 ms | 374 ms | 2.87 s | 9.72 s | 7.53 s |
| 8 | 190 ms | 288 ms | 2.22 s | 8.07 s | 6.30 s |
| 12 | 200 ms | 304 ms | 1.57 s | 6.10 s | 4.97 s |

## Live 5x comparison

All runs used 4 GiB pressure threshold, compact vision, unique caches, synthetic loopback RTSP, and reached capture-ready plus terminal stop.

| Threads | Duration after capture-ready | RTF range | Max observed L1 lag | Shared prefetch drops | Scheduler rejects | Scenario wall time | Peak RSS |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 25 s | 1.17–1.34 | 27.5 s | 3,083 | 32 | 47.21 s | 2.33 GiB |
| 8 | 25 s | 1.19–1.37 | 19.6 s | 2,885 | 46 | 47.68 s | 2.33 GiB |
| 12 | 25 s | 1.14–1.22 | 29.6 s | 3,390 | 15 | 42.83 s | 2.32 GiB |
| 4 | 60 s | 1.14–1.23 | 41.3 s | 6,074 | 37 | 86.94 s | 2.33 GiB |
| 12 | 60 s | 1.08–1.16 | 48.6 s | 6,864 | 47 | 80.43 s | 2.35 GiB |

Twelve threads improved RTF and wall time in the 60-second test, but raised pre-stop lag by 7.3 seconds and increased prefetch drops by 13% and scheduler rejects by 27%. Eight threads had the lowest lag and drops in the short check, but more scheduler rejects and no RTF improvement; an eight-thread 60-second soak was not run. Keep the default at four threads: the data does not establish a better balanced profile, and every tested 5x RTF remained above 1. These measurements do not verify physical-camera behavior.

Artifacts:

- Local model microbenchmark: [`embedding_thread_scale_20261026.md`](embedding_thread_scale_20261026.md) and [JSON](embedding_thread_scale_20261026.json).
- 25-second RTSP runs: [4 threads](live_rtsp_shared_dispatch_25s_20261026/report.json), [8 threads](live_rtsp_shared_dispatch_threads8_25s_20261026/report.json), [12 threads](live_rtsp_shared_dispatch_threads12_25s_20261026/report.json).
- 60-second RTSP runs: [4 threads](live_rtsp_shared_dispatch_60s_20261026/report.json), [12 threads](live_rtsp_shared_dispatch_threads12_60s_20261026/report.json).
