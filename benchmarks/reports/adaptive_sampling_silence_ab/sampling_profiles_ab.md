# Adaptive sampling performance A/B

Historical result for the earlier absolute-activity sampler. The current delta-based run is in
`../adaptive_sampling_delta_silence_ab_20261026/sampling_profiles_ab.md`.

Generated digital silence control; performance and heartbeat evidence only.

| Profile | Wall s | CPU s | CPU cores | RTF | Audio windows | Embeddings selected | Embeddings skipped |
|---|---:|---:|---:|---:|---:|---:|---:|
| standard | 18.258 | 17.891 | 0.980 | 0.10143 | 36 | 36 | 0 |
| adaptive | 17.785 | 17.078 | 0.960 | 0.09881 | 36 | 12 | 24 |

CPU seconds saved: 0.812 (4.5%); audio embedding reduction: 66.7%; audio consumer stage reduction: 44.4%.
Speech-presence top-1 accuracy on sampled silence windows: 0.0% standard and 0.0% adaptive. Accepted claims / accepted false positives: 0/0 standard, 0/0 adaptive.

This synthetic control does not establish recall on natural audio. Natural-window admission results are in `../adaptive_sampling_natural.md`; that 28-window exploratory set admitted every positive window but showed no selection reduction.
