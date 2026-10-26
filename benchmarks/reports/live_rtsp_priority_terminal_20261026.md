# Live RTSP priority check — 2026-10-26

## Setup

- Source: synthetic A/V fixture published in real time through local MediaMTX 1.21.2 and FFmpeg 8.1.1 to the SHSD API.
- Scale: two publishers and five publishers, 20 seconds requested per scenario.
- Load signal: `SHSD_MEMORY_LIMIT_BYTES=1` deliberately forced the admission controller into the critical path. This is not an operating-system memory cap.
- Stop handling: the runner waited up to 120 seconds for every DELETE-requested session to reach a terminal state. Both scenarios reached `stopped`.
- Raw measurements: [`report.json`](live_rtsp_priority_terminal_20261026/report.json), including snapshots, API latency samples, per-stream watermarks, worker metrics, and issue intervals.

## Results

| Scale | Capture ready | Capture wait | Stop to terminal | Wall time | Peak process-tree RSS | API latency p50 / p95 / max |
|---|---:|---:|---:|---:|---:|---:|
| 2x | yes | 26.629 s | 13.149 s | 60.584 s | 2.29 GiB | 15.633 / 44.901 / 556.201 ms (52 samples) |
| 5x | yes | 13.328 s | 53.265 s | 119.864 s | 2.33 GiB | 98.965 / 726.412 / 3,658.195 ms (45 samples) |

| Stream | Latest API capture C | Final processed L1/L2 R | Prefetch drops | Scheduler rejects | Terminal status |
|---|---:|---:|---:|---:|---|
| 2x-01 | 30,008 ms | 30,008 / 30,008 ms | 393 | 16 | stopped |
| 2x-02 | 25,636 ms | 20,536 / 20,536 ms | 262 | 17 | stopped |
| 5x-01 | 38,317 ms | 15,925 / 15,925 ms | 800 | 14 | stopped |
| 5x-02 | 43,052 ms | 25,174 / 25,174 ms | 955 | 18 | stopped |
| 5x-03 | 49,143 ms | 16,292 / 16,292 ms | 1,148 | 15 | stopped |
| 5x-04 | 48,326 ms | 16,018 / 16,018 ms | 1,123 | 14 | stopped |
| 5x-05 | 50,846 ms | 16,139 / 16,139 ms | 1,178 | 15 | stopped |

## Interpretation

The API and analysis process stayed within a measured 2.29–2.33 GiB process-tree RSS envelope while the injected critical-load signal activated admission control. The system completed shutdown for all seven sessions and exposed overload through prefetch drops, scheduler rejects, coverage issues, and watermark lag.

This run does not show sustained real-time processing. At 5x, the API capture cursor reached 38.3–50.8 seconds while the final processed L1/L2 cursor reached only 15.9–25.2 seconds. The 5x stop drain took 53.265 seconds. The reported API latency is request-to-watermark latency from polling snapshots, not end-to-end media latency.

The test uses loopback RTSP publishers, not a physical camera. It does not exercise automatic reconnect after an established RTSP session drops. Device enumeration on the host listed Meta Quest cameras and OBS Virtual Camera; no device stream was opened or captured.

## Acceptance status

This is evidence for bounded memory and explicit degradation on synthetic live RTSP at 2x/5x. F6.01 remains open pending runtime reconnect behavior and an authorized physical-camera capture. See [`Todo.md`](../../Todo.md) and [`Workspace.md`](../../Workspace.md).
