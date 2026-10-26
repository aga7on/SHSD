# Adaptive sampling performance A/B

Synthetic one_lsb_dither_unique_windows control; 3 paired repeats with isolated per-run caches and alternating execution order; performance and heartbeat evidence only.
Host: `AMD Ryzen 9 9900X3D 12-Core Processor`; `Microsoft Windows NT 10.0.26200.0`; 24 logical / 12 physical CPUs; 4 inference threads.

Profile rows show medians across repeats.

| Profile | Wall s | CPU s | CPU cores | RTF | Audio windows | Selected | Skipped | Cache hits | Inference ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| standard | 27.728 | 75.172 | 2.727 | 0.15404 | 36 | 36 | 0 | 0 | 14934.247 |
| adaptive | 19.912 | 44.172 | 2.228 | 0.11062 | 36 | 12 | 24 | 0 | 7259.578 |

Paired CPU savings median: 41.2% (range 40.1% to 41.3%); paired wall savings median: 28.2%; audio embedding reduction: 66.7%; paired audio-consumer stage savings median: 65.9%.
Paired model inference savings median: 51.3%; combined cache-hit rate: 0.0%.
Speech-presence top-1 accuracy on sampled silence windows: 0.0% standard and 0.0% adaptive. 
Accepted claims / accepted false positives: 0/0 standard, 0/0 adaptive.

This synthetic control does not establish recall on natural audio. See `../adaptive_sampling_natural_delta.md` for the separate 40-window exploratory admission report; its source-description labels still need independent listening review.

## Paired CPU results

| Repeat | Execution order | Standard CPU s | Adaptive CPU s | CPU saved |
|---:|---|---:|---:|---:|
| 1 | standard → adaptive | 75.156 | 44.172 | 41.2% |
| 2 | adaptive → standard | 75.172 | 44.094 | 41.3% |
| 3 | standard → adaptive | 76.719 | 45.953 | 40.1% |
