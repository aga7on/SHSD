# Live RTSP priority soak — 60 seconds, 2026-10-26

## Setup

- Local MediaMTX 1.21.2 + FFmpeg 8.1.1 synthetic A/V publishers connected to the SHSD API.
- Two-stream and five-stream scenarios; 60 seconds requested per scenario.
- `SHSD_MEMORY_LIMIT_BYTES=1` deliberately forced the critical-load admission path. It is not a host memory limit.
- The runner waited up to 120 seconds after DELETE for terminal status. All seven streams reached `stopped`.
- Raw snapshots and per-stream details: [`report.json`](live_rtsp_priority_60s_20261026/report.json).

## Results

| Scale | Capture ready | Stop wait | Wall time | Peak process-tree RSS | API polling p50 / p95 / max |
|---|---:|---:|---:|---:|---:|
| 2x | yes | 21.360 s | 107.843 s | 2.32 GiB | 14.931 / 53.609 / 244.973 ms (128 samples) |
| 5x | yes | 66.462 s | 195.561 s | 2.34 GiB | 95.133 / 10,866.451 / 11,301.742 ms (60 samples) |

| Scale | Combined prefetch drops | Combined scheduler rejects | Final L1 R cursor range |
|---|---:|---:|---:|
| 2x | 2,196 | 50 | 50,834–65,596 ms |
| 5x | 8,430 | 112 | 16,249–86,205 ms |

## Interpretation

The process-tree RSS remained within 2.32–2.34 GiB during both one-minute scenarios. Queue overflow and priority admission were visible in the recorded drop/reject counters. At 2x, API polling latency remained below 54 ms p95. At 5x, p95 polling latency rose to 10.87 seconds, stop drain took 66.462 seconds, and final L1 progress varied widely between streams. The system bounded memory and surfaced degradation, but did not signal degradation promptly enough to claim acceptable 5x live responsiveness or real-time processing.

The injected one-byte memory signal activates critical mode intentionally; measured RSS is reported separately. These loopback runs do not validate a physical camera, network behavior outside localhost, or long-duration thermal/soak behavior.
