# Shared load pressure and priority admission

Date: 2026-10-26.

## F6.01 progress

`RuntimeLoadController` now keeps external live-media/embedding/L1/ASR observations separate from semantic scheduler occupancy, then evaluates the more pressured queue while preserving source lag, CPU, RSS, and memory-limit signals. Its updates and reads are locked because decoder and consumer threads report load concurrently. `AsyncLevelScheduler` reports queued plus active jobs to that controller, so its own queue updates cannot erase an upstream pressure sample.

Priority bands are explicit in `WorkPriority`: P0 capture, P1 L0/embeddings, P2 L1, P3 L2/ASR, and P4 L3 narration. The timestamp merge uses P0 before P1 on ties. The common `admit()` decision is used by embedding, L1, ASR, `AsyncLevelScheduler`, and L3 admission. It allows work through P2 in critical mode, through P3 in degraded mode, and defers P4 until normal load. P3 ASR tasks may wait in a bounded deferred buffer; if load does not recover, the affected speech range is explicitly dropped.

The embedding worker, FIFO L1 worker, ASR worker, and `AsyncLevelScheduler` still have distinct bounded queues, now governed by one priority admission contract. L2 refinement remains post-analysis in file mode. Loopback RTSP stop and read-gap handling are covered, and bounded queues share the `admit()` contract. Physical-camera input, automatic reconnect after transport loss, and sustained live latency at 2x/5x remain open.

## Verification

- `pytest tests/unit -q`: 153 passed, including concurrent live/scheduler sampling and worker admission.
- `ruff check` on changed source and scheduler tests: passed.
- `mypy` on scheduler and worker modules: passed.
- `py_compile` on changed Python modules: passed.
- `mypy src/shsd/analyze.py` still reports that stubs for optional `psutil` are not installed; the prior narrator union-type finding was corrected.

Three end-to-end CPU smokes on `av_sync_20s.mp4` reached C/E/R(L1)/R(L2)=20,000 ms, produced 36 L1 matches, 31 L1 events, and 14 L2 events. The embedding worker completed 9/9 jobs and the L1 worker 12/12; maximum L1 outstanding reached 3/4 across runs. In the post-admission run, semantic scheduler rejects were zero and final load mode was `normal`; optional ASR was disabled. These are finite-file integration checks, not live-latency evidence.

## Concurrent 2x/5x smoke

A separate local-file concurrency smoke ran the shared-admission build against `av_sync_20s.mp4` with one cycle at each scale. Both scenarios passed: 2 streams completed in 16.32 s (aggregate RTF 0.408, mean 1.92 CPU cores, peak process-tree RSS 4,667 MiB); 5 streams completed in 18.50 s (aggregate RTF 0.1855, mean 4.77 CPU cores, peak RSS 11,677 MiB). Every stream reached C/E/R(L1)/R(L2)=20,000 ms with 36 matches; coverage misses, ingest drops, prefetch drops, and scheduler pressure rejects were all zero. Full machine-readable evidence and per-stream timelines are in `benchmarks/reports/shared_priority_scale_smoke_20261026/`. This is a one-cycle local-file smoke with a shared warm cache; it does not verify live-source priority, reconnect, or cold-cache latency.

