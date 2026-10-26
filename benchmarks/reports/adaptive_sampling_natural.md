# Adaptive sampling natural-window evaluation

Historical result for the absolute-activity sampler on the earlier 28-window set. The current
delta-based sampler and expanded 40-window evaluation are recorded in
`adaptive_sampling_natural_delta.md`.

- Windows: 28 (14 positive, 14 negative)
- Standard embeddings selected: 28/28
- Adaptive embeddings selected: 28/28
- Adaptive selection reduction: 0.0%
- Positive-window admission recall: 100.0%
- Synthetic silence control: 2/4 selected
- Reduction including synthetic silence control: 6.2%
- Heartbeat: every 15000 ms during low activity
- All positive windows admitted: True

This is an exploratory admission test, not semantic accuracy or a representative dataset.
The exact per-window decisions, activity scores, source grouping, and limitations are in the adjacent JSON.
