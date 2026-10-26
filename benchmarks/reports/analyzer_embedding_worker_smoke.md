# Bounded embedding worker smoke

Date: 2026-10-26  
Input: `tests/fixtures/media/av_sync_20s.mp4`  
Command: `shsd analyze ... --levels L0,L1 --threads 4 --offline --cpu-only`

## Result

- Media horizon: 20,000 ms; final C/E/D/R watermarks all reached 20,000 ms.
- Inference: 9 submitted, 9 completed, 0 failed; maximum outstanding work was 2 with a queue capacity of 2.
- L1: 36 window matches and 34 event revisions; the timeline completed without a worker error.
- Wall time: 32.48 s, including 13.66 s for model and profile initialization.
- Media interleave stage: 18.71 s; serial embedding inference: 18.63 s; result application: 38.5 ms.
- The video sampling gaps are explicitly recorded as `embedding_stride`; final watermarks report zero lag.

Raw timeline: [`analyzer_embedding_worker_smoke.jsonl`](analyzer_embedding_worker_smoke.jsonl).

This run checks boundedness, ordered result application, and coverage on one local fixture. It is not a sync-versus-worker speed comparison and does not establish live RTSP latency or sustained multi-stream performance.
