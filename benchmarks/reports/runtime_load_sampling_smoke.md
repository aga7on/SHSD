# Runtime load sampling smoke

Date: 2026-10-26.

## Change

`analyze_media()` now feeds the shared `RuntimeLoadController` nonblocking samples during the media interleave, at most once per 250 ms. Each sample uses the most occupied prefetch or embedding queue, current `C−E` lag, host CPU, and current process-tree RSS. The resource sampler refreshes CPU/RSS every 50 ms. A forced sample after draining inference lets the controller recover before post-pass L2 admission.

## Verification

Ran `shsd analyze tests/fixtures/media/av_sync_20s.mp4 --cpu-only --levels L0,L1,L2 --threads 4 --prefetch-capacity 8` with isolated output and event storage.

- C/E/R(L1)/R(L2) all reached 20,000 ms.
- 14 L2 events committed; scheduler pressure rejects: 0.
- Five runtime load observations were recorded; host metrics were available and the final controller mode was `normal`.
- Peak process-tree RSS: 2,432,446,464 bytes. The final system CPU sample was 10.9%.

This confirms the load observation and downstream admission path on one finite local A/V run. It does not validate live queue priorities or sustained 2×/5× source latency.
