# Analyzer prefetch drop-policy smoke

## Purpose

Exercise the nonblocking overflow path inside the real `analyze_media()` A/V producer/consumer pipeline and verify that dropped inference work remains visible as coverage. This uses a local file with an intentionally tiny queue; it does not simulate a camera/RTSP source or establish sustained 2x/5x performance.

## Run

```powershell
.\.venv\Scripts\shsd.exe analyze tests\fixtures\media\av_sync_20s.mp4 --levels L0,L1,L2 --cpu-only --offline --threads 4 --window-seconds 5 --prefetch-capacity 1 --prefetch-overflow-policy drop_oldest --stream-id analyzer-prefetch-drop-smoke --output benchmarks\reports\analyzer_prefetch_drop_smoke.jsonl
```

The run used the pinned local CPU embedding model and took 12.959 s including model/profile initialization. The process-tree RSS peak was 2,431,299,584 bytes. `RuntimeLoadController` remained `normal`; semantic scheduler backpressure count was zero.

## Results

| Queue | Capacity / peak | Policy | Dropped queue items | Producer block episodes |
|---|---:|---|---:|---:|
| Audio | 1 / 1 | `drop_oldest` | 127 | 0 |
| Video | 1 / 1 | `drop_oldest` | 215 | 0 |

The merged admission heap held at most 2/2 lookahead items and dispatched 822 items. Final C/E/R cursors reached 20,000 ms. Those cursor values include terminal dropped/skipped spans and do not mean every embedding completed. The final E coverage contains three explicit video embedding drops: `[5000,5001)`, `[10000,10001)`, and `[15000,15001)` ms, each with reason `prefetch_queue_full`. The producer also dropped capture-span notifications; their original C status was recorded by the callback so capture coverage still reached 20,000 ms.

This confirms the configured bounded queues remain at capacity and report losses without blocking the producer. It is a single 20-second local-file run and does not close F6.01's live-source or sustained-load acceptance criteria.

Validation at this revision: 145 unit tests; Ruff across `src`, `tests`, and `scripts`; mypy across 44 source files.
