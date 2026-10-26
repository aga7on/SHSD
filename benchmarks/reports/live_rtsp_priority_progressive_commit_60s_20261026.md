# Live RTSP progressive watermark acceptance — 2026-10-26

## Setup

- Local MediaMTX + FFmpeg synthetic A/V publishers; API loopback, two streams followed by five.
- 60 seconds of observation per scale, 4 threads per stream, `window_ms=5000`.
- `SHSD_MEMORY_LIMIT_BYTES=4294967296` (4 GiB); this is a runtime pressure input, not a system memory cap.
- Raw snapshots: [`report.json`](live_rtsp_priority_progressive_commit_60s_20261026/report.json).

## Results

| Scale | Streams terminal | Pre-stop R[L1] range | API latency p95 / max | Peak process-tree RSS | Shared prefetch drops | Stop wait |
|---|---:|---:|---:|---:|---:|---:|
| 2x | 2/2 | 60.7–64.1 s | 48 / 64 ms | 2.33 GiB | 163 | 0.60 s |
| 5x | 5/5 | 31.1–41.1 s | 295 / 460 ms | 2.35 GiB | 2,449 | 27.63 s |

All seven streams reached terminal `stopped`; no L1 worker failures or semantic scheduler rejects were recorded. The maximum observed pre-stop L1 lag was 5.0 seconds at 2x and 7.6 seconds at 5x. Final watermarks caught up after stop and queue drain.

## Interpretation

The analyzer previously left live R[L1] at zero because completed-window coverage began after a small initial PTS offset, leaving the contiguous cursor blocked at zero. The analyzer now records that leading interval as an explicit `gap`, records audio E coverage before the first audio window, and advances the source horizon only from captured media. A 12-second 2x/5x recheck showed nonzero pre-stop R[L1] on every stream.

The 5x run still drained for 27.63 seconds after stop and accumulated 2,449 shared-prefetch drops. This confirms visible progressive commits and bounded process memory on synthetic loopback RTSP; it does not establish continuous real-time processing at 5x or behavior with a physical camera.
