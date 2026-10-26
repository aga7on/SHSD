# Full-stack feature A/B results

Generated from the local benchmark JSON reports listed in `fullstack_feature_ab.json`. Runs used the same synthetic A/V fixture and 2x/5x stream scale unless stated otherwise.

## L3 caption backend

| Scale | Backend | Per-stream RTF p50/p95 | Peak process-tree RSS (MiB) | Caption latency p50/p95 (ms) | Generation throughput (tokens/s) |
|---:|---|---:|---:|---:|---:|
| 2x | template | 0.867/0.867 | 4675 | 0.012/0.034 | no generation |
| 2x | Qwen | 1.288/1.299 | 6246 | 3466/4484 | 30.9 |
| 5x | template | 0.984/0.989 | 11678 | 0.019/0.044 | no generation |
| 5x | Qwen | 1.704/1.708 | 15608 | 5779/7398 | 12.3 |

Template mode produced source-only fallback captions in 4/4 and 10/10 calls, with zero unsupported claims. Its caption construction took under 0.05 ms p95. Qwen generated 2 captions and fell back on 2/4 calls at 2x, and generated 5/fell back on 5/10 at 5x. Qwen measured 30.9 and 12.3 tokens/s, with caption latency p50/p95 of 3.47/4.48 s and 5.78/7.40 s. The Qwen path pushed per-stream RTF above 1 at both scales; template stayed below 1. Treat template as a bounded safe fallback, and do not run Qwen narration on the 5x profile without scheduling/degradation.

All caption A/B scenarios had zero unsupported claims, coverage misses, and scheduler rejects. These are one-cycle measurements on synthetic A/V, not a broad quality or concurrency evaluation.

## GigaAM ASR on/off

| Scale | ASR | Per-stream RTF p50/p95 | Peak process-tree RSS (MiB) | Segments | ASR errors / drops |
|---:|---|---:|---:|---:|---:|
| 2x | off | 3.238/3.239 | 4,029 | 0 | 0 / 0 |
| 2x | on | 3.769/3.790 | 7,946 | 2 | 0 / 0 |
| 5x | off | 3.780/3.781 | 10,091 | 0 | 0 / 0 |
| 5x | on | 4.298/4.320 | 19,834 | 5 | 0 / 0 |

The input was a single 5.016-second synthetic Russian speech fixture, so startup dominates these RTF values. ASR adds substantial runtime and memory in this smoke; it should remain opt-in pending longer-media measurements. It emitted segments without reported ASR errors or ingest/coverage drops.

## Dynamic `music_presence` hypotheses

| Scale | Mode | RTF p50/p95 | Peak RSS (MiB) | Proposal result | Selected dynamic candidates |
|---:|---|---:|---:|---|---:|
| 2x | baseline | 0.862/0.867 | 4,681 | not requested | 0 |
| 2x | dynamic | 1.329/1.334 | 6,248 | 3 candidates; proposal latency p50/p95 8,477/8,707 ms | 0 |
| 5x | baseline | 0.980/0.981 | 11,665 | not requested | 0 |
| 5x | dynamic | 1.538/1.538 | 15,558 | 5 proposal calls timed out at 10 s; no candidates | 0 |

A separate 28-window natural-media evaluation had identical baseline and iterative ranked accuracy (17/28, 0.607), zero accepted claims, and zero coverage. It provides no measured quality gain. Keep dynamic proposals opt-in; the measured latency, absence of selected candidates, and 5x timeouts make the current path unsuitable as a default.

## Scheduler pressure regression check

After admission was changed to use current prefetch depth instead of the stale peak depth, the 2x and 5x one-cycle recheck both completed with zero scheduler pressure rejects, zero coverage misses, and zero prefetch drops. This isolates the false end-of-file rejection seen in the earlier 10-minute run; it does not replace the long soak now in progress.

## Decision

- Keep the template narrator as the fast source-only fallback.
- Keep Qwen L3 and GigaAM ASR opt-in at multi-stream scale until the scheduler can degrade or defer them within the latency and memory budget.
- Keep dynamic hypothesis generation opt-in; no quality uplift was observed, and proposals time out under 5x load.
- Do not mark F6.03 complete until the 30-minute 2x/5x baseline soak finishes and its CPU, RAM, lag, disk queue, and coverage evidence is reviewed.
