# Live RTSP priority and graceful stop recheck — 2026-10-26

## What changed

- Video embedding stride now expands under shared source pressure: at least 2× the window for 2+ sources and 4× for 5+ sources. This reduces video inference admission while retaining bounded capture and explicit `runtime_backpressure` coverage.
- L1 `D`/`R` revisions are selected and applied atomically inside `WatermarkTracker`. The same path handles initial semantic gaps, preventing runtime skips and L1 results from racing with duplicate revisions.
- A PyAV read or decoder flush error after an explicit stop is treated as graceful shutdown. An unexpected stop-time exception is retained in the API `error` field instead of being silently hidden.
- Embedding metrics separate model inference time from time spent waiting in the shared worker.

## Run

`scripts/benchmark_live_rtsp_priority.py` generated distinct synthetic A/V RTSP sources for 2 and 5 concurrent streams. Each phase ran for 25 seconds with four CPU threads per shared provider, a 4 GiB load-controller memory threshold, a 5-second window, `drop_oldest` prefetch, and a fresh embedding cache. The two phases ran sequentially in one API process, so the 5× phase reused initialized model profiles. This is loopback integration evidence, not a physical-camera run or an endurance soak.

Raw measurements: [`report.json`](live_rtsp_priority_graceful_stop_final_20261026/report.json).

## Results

| Scale | Wall time | DELETE-to-stopped | Pre-stop `R[L1]` | Final `C/E/R[L1]` | End-to-end ratio* | Peak process-tree RSS |
|---|---:|---:|---|---|---|---:|
| 2× | 62.35 s | 5.25 s | 15.1 s, 30.2 s | 34.9 s, 35.0 s | 1.65–1.75 | 2.37 GiB |
| 5× | 44.44 s | 5.01 s | 5.1 s, 10.1 s, 5.1 s, 5.1 s, 0.053 s | 34.2 s, 33.8 s, 33.6 s, 33.2 s, 32.9 s | 1.18–1.28 | 2.37 GiB |

All seven streams reached terminal `stopped`, preserved metrics, ended with equal final `C`, `E`, and `R[L1]`, and had no pending coverage intervals. There were no L1 worker errors. Shared prefetch reported 833 drops at 2× and 3,447 at 5×. Five-stream video admission recorded 96 runtime-backpressure skips. API polling latency at 5× was p95 231.6 ms and max 333.3 ms.

The end-to-end ratio is job elapsed time divided by final committed media duration; it includes initialization and post-stop drain. It is above 1 at both scales, so this run does not establish sustained real-time throughput. At 5×, one stream had only 53 ms of `R[L1]` before DELETE, with the remaining coverage completed during shutdown drain. Physical-camera validation remains open.

## Verification

- Full suite: 175 passed.
- Ruff: passed for changed modules and tests.
- Mypy: passed for changed production modules with missing third-party stubs ignored (`psutil` and `threadpoolctl` are installed without type stubs in this venv).
- `compileall`: passed before the final watermark revision fix; the subsequent full pytest import/collection and mypy checks also validated the final files.

Reproduction command:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_live_rtsp_priority.py `
  --mediamtx C:\Users\ARTEM\AppData\Local\Temp\shsd-mediamtx-1.21.2\mediamtx.exe `
  --ffmpeg C:\Users\ARTEM\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe `
  --shsd X:\AI\SHSD\.venv\Scripts\shsd.exe `
  --duration-seconds 25 --threads 4 --memory-limit-bytes 4294967296 `
  --stop-timeout-seconds 120 `
  --output-dir X:\AI\SHSD\benchmarks\reports\live_rtsp_priority_graceful_stop_final_20261026
```
