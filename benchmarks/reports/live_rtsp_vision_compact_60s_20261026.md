# Compact vision profile live RTSP soak ? 2026-10-26

## Setup

Local MediaMTX + FFmpeg synthetic A/V over RTSP, four CPU threads, 4 GiB runtime memory threshold, compact 140-token vision profile, two streams followed by five streams for 60 seconds each. The shared API/provider process stayed up between scales. Raw timelines and metrics: [`report.json`](live_rtsp_vision_compact_60s_20261026/report.json). The benchmark runner now accepts `--vision-profile standard|compact` and records the setting.

All streams reached terminal `stopped` without analysis errors. Final C/E/R[L1] aligned on every stream after stop and drain.

| Concurrent streams | Max observed positive C?R[L1] lag before stop | Shared prefetch drops | Scheduler pressure rejects | Embedding jobs submitted | Stop wait | API p95 / max | Peak process-tree RSS | Elapsed / final media span |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 8.1 s | 503 | 0 | 38 | 0.32 s | 49 / 151 ms | 2.35 GiB | 1.31x |
| 5 | 40.1 s | 5,918 | 28 | 8 | 5.94 s | 330 / 406 ms | 2.37 GiB | 1.08?1.15x |

The 2x run had materially fewer drops and rejects than the earlier four-thread standard-profile soak with the same 4 GiB threshold (1,618 drops and 35 rejects), and more embedding jobs completed (38 vs. 28). At 5x, compact did not improve overload behavior: 5,918 drops and 28 rejects versus 5,839 and 31 in the standard run; the maximum observed positive L1 lag was 40.1 s versus 37.6 s. These are separate runs, not an interleaved controlled A/B, so treat the comparison as directional.

## Interpretation

Compact detail improved the measured 2x run but did not make five concurrent live streams sustainable on this CPU. The final watermarks align because the service drains admitted work after stop; this is not proof of bounded live latency. Physical camera behavior is still unverified. Keep the profile opt-in and keep F6.01 open.

## Reproduction

```powershell
python scripts/benchmark_live_rtsp_priority.py --mediamtx PATH_TO_MEDIAMTX --ffmpeg PATH_TO_FFMPEG --shsd .venv/Scripts/shsd.exe --output-dir benchmarks/reports/live_rtsp_vision_compact_60s_20261026 --duration-seconds 60 --threads 4 --memory-limit-bytes 4294967296 --stop-timeout-seconds 180 --vision-profile compact
```
