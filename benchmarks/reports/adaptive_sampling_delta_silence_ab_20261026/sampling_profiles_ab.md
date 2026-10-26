# Adaptive sampling performance A/B

Historical single-run result on pure digital silence. Identical PCM windows hit the embedding cache; the later 600-second control records this limitation, and the repeated unique-window inference control is `../adaptive_sampling_delta_quiet_paired_180s_20261026/sampling_profiles_ab.md`.

Generated digital silence control; performance and heartbeat evidence only.

| Profile | Wall s | CPU s | CPU cores | RTF | Audio windows | Embeddings selected | Embeddings skipped |
|---|---:|---:|---:|---:|---:|---:|---:|
| standard | 15.310 | 14.969 | 0.978 | 0.08505 | 36 | 36 | 0 |
| adaptive | 15.248 | 14.875 | 0.976 | 0.08471 | 36 | 12 | 24 |

CPU seconds saved: 0.094 (0.6%); audio embedding reduction: 66.7%; audio consumer stage reduction: 2.9%.
Speech-presence top-1 accuracy on sampled silence windows: 0.0% standard and 0.0% adaptive. 
Accepted claims / accepted false positives: 0/0 standard, 0/0 adaptive.

This synthetic control does not establish recall on natural audio. See `../adaptive_sampling_natural_delta.md` for the separate 40-window exploratory admission report; its source-description labels still need independent listening review.
