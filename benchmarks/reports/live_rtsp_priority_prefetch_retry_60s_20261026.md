# RTSP prefetch retry soak — 2026-10-26

## Run conditions

The local loopback benchmark used synthetic audio/video RTSP sources at 2x and 5x concurrency, with each phase streaming for 60 seconds. Both phases used four CPU threads per shared provider, a 4 GiB memory threshold, 5-second windows, `drop_oldest` prefetch, and an isolated embedding cache. The 5x phase followed the 2x phase in the same API process, so model initialization was warm. This run used MediaMTX 1.21.2; it did not use a physical camera.

Raw samples are in [`report.json`](live_rtsp_priority_prefetch_retry_60s_20261026/report.json).

## Results

| Scale | Wall time | Stop wait | Pre-stop `R[L1]` | Final `C/E/R[L1]` | End-to-end ratio* | Peak process-tree RSS |
|---|---:|---:|---|---|---:|---:|
| 2x | 93.07 s | 1.41 s | 15.01–15.15 s | 69.40–69.72 s | 1.321–1.344 | 2.38 GiB |
| 5x | 88.76 s | 12.80 s | 0.35–15.33 s | 69.22–70.15 s | 1.073–1.250 | 2.42 GiB |

All seven sessions reached `stopped` without errors. Final C, E, and R[L1] matched for each stream. Shared prefetch dropped 1,618 items at 2x and 5,839 at 5x. Standard video sampling selected 6 embedding opportunities at 2x and 21 at 5x, with 25 and 96 `runtime_backpressure` skips. API polling p95/max latency was 52.39/214.55 ms at 2x and 258.71/341.19 ms at 5x.

The end-to-end ratio is job elapsed time divided by final committed media duration; it includes startup and stop drain. It remained above 1 at both scales. Pre-stop 5x lag varied from 0.35 to 15.33 seconds, so this run does not establish steady real-time throughput. A prior one-minute run recorded three selected video embedding opportunities at 5x; the new run recorded 21. These are separate runs, so the difference is an observation rather than a controlled A/B result.

## Code and verification

When a selected video frame is discarded by bounded prefetch, its stride reservation is now released. The next decoded frame can be selected, while E coverage still records the discarded frame as dropped. Adaptive sampling also rolls back its last selected video timestamp. Regression coverage exercises the drop callback and a subsequent retry.

Verification after the change: 178 unit tests passed; Ruff passed; Mypy passed for `analyze.py` and `sampling.py`.

F6.01 remains open for sustained live progress and physical-camera validation.

## Reproduction

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_live_rtsp_priority.py `
  --mediamtx C:\Users\ARTEM\AppData\Local\Temp\shsd-mediamtx-1.21.2\mediamtx.exe `
  --ffmpeg C:\Users\ARTEM\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe `
  --shsd X:\AI\SHSD\.venv\Scripts\shsd.exe `
  --duration-seconds 60 --threads 4 --memory-limit-bytes 4294967296 `
  --stop-timeout-seconds 180 `
  --output-dir X:\AI\SHSD\benchmarks\reports\live_rtsp_priority_prefetch_retry_60s_20261026
```
