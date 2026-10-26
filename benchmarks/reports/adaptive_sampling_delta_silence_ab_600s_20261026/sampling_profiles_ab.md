# Adaptive sampling performance A/B

Generated digital silence control; performance and heartbeat evidence only.

Host: AMD Ryzen 9 9900X3D 12-Core Processor; Microsoft Windows NT 10.0.26200.0; 24 logical CPUs; four inference threads.

| Profile | Wall s | CPU s | CPU cores | RTF | Audio windows | Embeddings selected | Embeddings skipped |
|---|---:|---:|---:|---:|---:|---:|---:|
| standard | 55.257 | 55.906 | 1.012 | 0.09209 | 120 | 120 | 0 |
| adaptive | 56.587 | 56.484 | 0.998 | 0.09431 | 120 | 40 | 80 |

CPU seconds saved: -0.578 (-1.0%); audio embedding reduction: 66.7%; audio consumer stage reduction: 11.7%.
Speech-presence top-1 accuracy on sampled silence windows: 0.0% standard and 0.0% adaptive. 
Accepted claims / accepted false positives: 0/0 standard, 0/0 adaptive.

This synthetic control does not establish recall on natural audio. See `../adaptive_sampling_natural_delta.md` for the separate 40-window exploratory admission report; its source-description labels still need independent listening review.

Cache diagnostic: 120/120 standard and 40/40 adaptive embedding jobs were cache hits, and measured model inference was 0 ms in both profiles. All 5-second PCM windows in this pure digital-silence source are identical, so this run measures the surrounding pipeline and skip bookkeeping, not saved model inference.
