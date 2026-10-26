# RTSP loopback CPU thread-count experiment - 2026-10-26

## Change

`scripts/benchmark_live_rtsp_priority.py` now accepts `--threads` (default 1, preserving the earlier baseline) and records `threads_per_stream` in `report.json`. The API already shares one local embedding provider across matching streams; the benchmark now exercises its existing thread-count setting instead of hardcoding one thread.

## Method

MediaMTX 1.21.2 and FFmpeg 8.1.1 published synthetic audio/video over localhost RTSP. Each 2x and 5x scenario captured for 60 seconds. `SHSD_MEMORY_LIMIT_BYTES=1` injected the critical-admission signal; it was not an OS memory cap. The model stayed on CPU with its existing bfloat16 checkpoint. The one-thread baseline is `live_rtsp_priority_async_metadata_20261026/report.json`; the four-thread run is in this directory.

A warmed single-provider microbenchmark encoded 15 distinct five-second speech windows after three warmups at each thread count:

| Threads | Inference p50 | Inference p95 |
|---:|---:|---:|
| 1 | 581.8 ms | 596.2 ms |
| 2 | 426.4 ms | 456.1 ms |
| 4 | 263.6 ms | 265.9 ms |

The four-thread audio vectors matched the one-thread vectors on 12 windows after normalization (minimum cosine 0.999999999998); no tested window fell below 0.9999.

## 60-second live results

All streams in both runs reached terminal `stopped`. L1 lag below is measured after stop and drain.

| Threads | Streams | API p50 / p95 / max | Stop wait | Peak process-tree RSS | Prefetch drops | Scheduler rejects | Embedding jobs / inference time | Final L1 lag |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2x | 10.0 / 40.7 / 467.3 ms | 30.966 s | 2.307 GiB | 1,799 | 68 | 28 / 126.0 s | 4.747-5.260 s |
| 4 | 2x | 14.8 / 47.9 / 426.7 ms | 2.576 s | 2.343 GiB | 608 | 95 | 46 / 39.7 s | 0 s |
| 1 | 5x | 104.6 / 298.4 / 435.5 ms | 48.744 s | 2.321 GiB | 4,371 | 118 | 45 / 374.0 s | 15.207-17.410 s |
| 4 | 5x | 111.1 / 284.0 / 508.2 ms | 15.030 s | 2.347 GiB | 2,723 | 168 | 64 / 230.0 s | 0-3.470 s |

At 5x, four threads increased completed embedding jobs from 45 to 64, reduced aggregate inference time by 38%, reduced prefetch drops by 38%, and reduced post-drain L1 lag to at most 3.47 seconds. API p95 improved slightly; maximum latency and scheduler rejects increased. At 2x, shutdown and final L1 drain were much faster. Peak RSS stayed below 2.35 GiB but came close to that measured limit.

## Limits and reproduction

These are synthetic loopback streams under an injected critical-load signal. Final L1 lag is measured after capture stops; this run does not establish uninterrupted real-time analysis, physical-camera behavior, WAN transport, or thermal stability. Tune threads against the deployment CPU and memory budget. Keep F6.01 open.

Reproduce the four-thread run with:

```powershell
python scripts/benchmark_live_rtsp_priority.py --mediamtx C:\Users\ARTEM\AppData\Local\Temp\shsd-mediamtx-1.21.2\mediamtx.exe --duration-seconds 60 --threads 4 --output-dir benchmarks\reports\live_rtsp_priority_threads4_60s_20261026
```

Raw JSON is `report.json`. The benchmark harness passes Ruff, Python compilation, and the integration run exits successfully.
