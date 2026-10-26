# Live RTSP metadata persistence responsiveness ? 2026-10-26

## Change

Live watermark and analysis checkpoints are now queued to a shared background writer. Updates coalesce to the newest snapshot per stream, so the API event loop does not wait for SQLite on every watermark. The writer queue has one drain task per `StreamManager`; terminal states still synchronously persist from a worker thread. `api_metadata_checkpoints_coalesced` reports how many pending snapshots were replaced.

## Setup

- MediaMTX 1.21.2 and FFmpeg 8.1.1 generated synthetic audio/video over localhost RTSP.
- The API ran 2 and 5 concurrent streams, with `SHSD_MEMORY_LIMIT_BYTES=1` to force the critical admission path. This is an injected signal, not an OS memory cap.
- All measurements are loopback synthetic live-source tests; they do not validate a physical camera, WAN transport, or thermal soak.

## 60-second run

| Streams | Polls | API p50 / p95 / max | Stop wait | Peak process-tree RSS | Prefetch drops | Scheduler rejects | Final L1 lag range |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2x | 130 | 10 / 42 / 467 ms | 30.966 s | 2.307 GiB | 1,799 | 68 | 4.747?5.260 s |
| 5x | 200 | 107 / 299 / 435 ms | 48.744 s | 2.321 GiB | 4,371 | 118 | 15.207?17.410 s |

The earlier 60-second run, before moving checkpoint writes off the event loop, measured 5x API polling at p95/max 10.876/11.302 s, a 66.462 s stop wait, 8,430 prefetch drops, 112 scheduler rejects, and 2.344 GiB peak RSS. The updated 5x p95 is about 36 times lower. The remaining L1 lag shows that inference throughput still trails capture at 5x; this run does not establish real-time analysis.

## Final-code 25-second smoke

A second run was made after consolidating persistence scheduling to one drain task per manager.

| Streams | API p50 / p95 / max | Stop wait | Peak process-tree RSS | Prefetch drops | Scheduler rejects | Final C/R(L1) |
|---|---:|---:|---:|---:|---:|---:|
| 2x | 12 / 40 / 782 ms | 22.941 s | 2.286 GiB | 118 | 54 | 31.934?35.454 s, equal |
| 5x | 105 / 253 / 387 ms | 42.112 s | 2.297 GiB | 291 | 154 | 31.116?36.214 s, equal |

All streams reached terminal state in both scenarios. In the short run, L1 caught up to captured coverage after stop and queue drain; the 42.112 s 5x drain time remains material.

## Reproduction and raw data

- 60-second run: `scripts/benchmark_live_rtsp_priority.py --mediamtx <mediamtx.exe> --duration-seconds 60 --output-dir benchmarks/reports/live_rtsp_priority_async_metadata_20261026`
- Final-code smoke: same command with `--duration-seconds 25 --output-dir benchmarks/reports/live_rtsp_priority_async_metadata_smoke_20261026`
- Raw JSON is in each output directory as `report.json`.
- API unit coverage verifies a blocked SQLite checkpoint does not block watermark publication and that queued snapshots coalesce to the latest state.
