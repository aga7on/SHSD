# RTSP stalled-read cancellation and live watermark smoke

Date: 2026-10-26. This is a loopback smoke using MediaMTX and FFmpeg; it is not a physical-camera test.

## Stop while the RTSP read was stalled

Stream `stall-read-check4` remained `running` while the video capture cursor held at 19,067 ms for more than 1.2 seconds. `DELETE /v1/streams/stall-read-check4` returned in 9 ms. The replayed API events show `stream.stopping` at `2026-10-26T02:24:46.081733Z` and `stream.stopped` at `2026-10-26T02:24:46.500635Z`, a stop-to-terminal interval of 418.9 ms. The final status was `stopped` with no error.

This cancellation measurement was captured before the watermark change below. The change does not touch stop handling.

## Video-only RTSP watermark after the fix

For a live source with unknown duration and no audio track, `analyze_media()` now marks unavailable C/E intervals through each emitted progress horizon. It uses `WatermarkTracker.mark_uncovered()`, preserving any coverage already recorded for that interval.

The post-change WebSocket replay for video-only stream `stall-read-fixed-02` recorded these live snapshots:

| source horizon | Overall C | audio C (unavailable) | video C | Overall E |
|---:|---:|---:|---:|---:|
| 1,051 ms | 1,051 ms | 1,051 ms | 1,051 ms | 0 ms |
| 2,051 ms | 2,051 ms | 2,051 ms | 2,051 ms | 0 ms |
| 3,051 ms | 3,051 ms | 3,051 ms | 3,051 ms | 0 ms |

After the finite publisher ended, the stream completed without an error at C/E=5,751 ms. This confirms overall capture progress advances during a live video-only stream; embedding E can still lag capture while inference is pending.

## Limits

The stop test exercises a loopback RTSP read gap, not camera reconnect or physical-device behavior. F6.01 now shares load pressure across live media and semantic scheduling and defines P0-P4 priorities, while the common dispatch contract and sustained live-load latency remain open.

## Subsequent F6.01 progress (2026-10-26)

The common `RuntimeLoadController.admit()` policy is now called by the embedding, L1, ASR, semantic scheduler, and L3 lanes at P1-P4; P0 capture/drop coverage retains tie precedence. The bounded lane queues remain distinct. Worker admission tests and the concurrent 2x/5x local-file smoke are recorded in `shared_load_priority_scheduler.md`. This does not add automatic reconnect or certify physical-camera input.
