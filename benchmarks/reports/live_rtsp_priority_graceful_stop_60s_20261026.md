# Live RTSP priority and graceful stop soak — 2026-10-26

## Run conditions

The loopback benchmark used synthetic audio/video RTSP sources at 2× and 5× concurrency, each phase streaming for 60 seconds. The API used four CPU threads per shared provider, a 4 GiB memory threshold, 5-second windows, `drop_oldest` prefetch, and an isolated embedding cache. The 5× phase ran after 2× in the same API process, so model/profile initialization was warm. This is a one-minute soak, not a physical-camera test.

Raw samples are in [`report.json`](live_rtsp_priority_graceful_stop_60s_20261026/report.json).

## Results

| Scale | Wall time | DELETE-to-stopped | Pre-stop `R[L1]` | Final `C/E/R[L1]` | End-to-end ratio* | Peak process-tree RSS |
|---|---:|---:|---|---|---|---:|
| 2× | 94.04 s | 2.28 s | 20.2 s, 15.1 s | 69.5 s, 69.5 s | 1.31–1.34 | 2.42 GiB |
| 5× | 82.68 s | 6.39 s | 10.2 s, 5.1 s, 0.182 s, 0.265 s, 0.084 s | 69.7 s, 70.0 s, 69.8 s, 70.0 s, 69.8 s | 1.09–1.15 | 2.36 GiB |

All seven jobs stopped without errors and published metrics. Final C/E/R[L1] aligned for every stream with zero pending coverage. Non-done statuses remain visible as explicit gaps/skips/drops: 149 final issues at 2× and 169 at 5×. Shared prefetch reported 1,826 drops at 2× and 5,255 at 5×. Standard-profile video sampling recorded 21/96 `runtime_backpressure` skips. API polling latency p95/max was 48.3/431.0 ms at 2× and 317.6/538.6 ms at 5×.

The end-to-end ratio is job elapsed time divided by final committed media duration; it includes startup and stop drain. It stays above 1 at both scales. Pre-stop L1 progress at 5× remained uneven: three streams were below 0.3 seconds when DELETE was requested, and the final drain then advanced them to approximately 70 seconds. The run therefore does not establish sustained real-time throughput.

## Engineering path

The run keeps memory bounded and preserves the entire terminal timeline, but the shared inference path cannot keep all five streams current. Keep capture/drop priority and the existing bounded queues; next, profile the shared embedding worker at several thread allocations and test whether its serial inference admission can be batched or scheduled with better fairness. Re-run the same one-minute scenario and compare pre-stop L1 lag, queue drops, API latency, and peak RSS. F6.01 remains open until sustained live progress and physical-camera behavior are verified.

## Reproduction

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_live_rtsp_priority.py `
  --mediamtx C:\Users\ARTEM\AppData\Local\Temp\shsd-mediamtx-1.21.2\mediamtx.exe `
  --ffmpeg C:\Users\ARTEM\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe `
  --shsd X:\AI\SHSD\.venv\Scripts\shsd.exe `
  --duration-seconds 60 --threads 4 --memory-limit-bytes 4294967296 `
  --stop-timeout-seconds 180 `
  --output-dir X:\AI\SHSD\benchmarks\reports\live_rtsp_priority_graceful_stop_60s_20261026
```
