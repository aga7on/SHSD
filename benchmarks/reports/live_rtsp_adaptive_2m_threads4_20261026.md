# Adaptive-profile live RTSP soak, 2 minutes

Date: 2026-10-26. A synthetic A/V loopback run compared the `adaptive` sampling profile with the existing `standard` 4-thread / 5-second-window baseline. Both used isolated caches, compact vision, a 4 GiB configured memory limit, and 120 seconds per 2x and 5x scenario. Every scenario reached capture-ready and every source reached a terminal state. Peak process-tree RSS remained below 2.36 GiB.

RTF is per-stream end-to-end elapsed time divided by final captured media seconds. Peak L1 lag is the largest sampled per-stream L1 lag during capture. Final R/L1 issue coverage sums typed `gap` and `skipped` spans against captured source media; adaptive sampling skips are therefore visible in this coverage figure. Prefetch drops and scheduler rejects are summed across sources. Synthetic inputs measure scheduling and compute only; they do not establish semantic recall.

| Scale | Profile | RTF median / max | Peak L1 lag | Final R/L1 issue spans | Audio / image embeddings | Prefetch drops / rejects | Peak RSS | Final load states |
|---|---|---:|---:|---:|---:|---:|---:|---|
| 2x | Standard | 1.139 / 1.141 | 5.9 s | 0.3% | 50 / 24 | 282 / 86 | 2.32 GiB | normal / normal |
| 2x | Adaptive | 1.142 / 1.144 | 5.8 s | 64.7% | 18 / 24 | 373 / 127 | 2.33 GiB | critical / normal |
| 5x | Standard | 1.065 / 1.087 | 56.8 s | 81.7% | 18 / 6 | 11,360 / 63 | 2.35 GiB | 4 critical / 1 normal |
| 5x | Adaptive | 1.089 / 1.110 | 65.1 s | 89.9% | 8 / 5 | 10,804 / 41 | 2.36 GiB | 4 critical / 1 normal |

At 2x, adaptive sampling reduced audio embeddings from 50 to 18, with the image count unchanged, but increased final R/L1 issue coverage from 0.3% to 64.7%; 160 seconds of the reported issue spans were marked `adaptive_sampling`. RTF and peak lag were effectively unchanged, and one source ended in critical load.

At 5x, adaptive sampling reduced audio/image embeddings from 18/6 to 8/5 and reduced prefetch drops by about 5%. It did not improve end-to-end RTF: median/max rose from 1.065/1.087 to 1.089/1.110. Peak L1 lag rose by 8.3 seconds and final R/L1 issue coverage rose from 81.7% to 89.9%; most adaptive-run issue coverage was `not_processed` gaps under sustained queue pressure. Four of five sources ended in critical load for both profiles.

Keep adaptive sampling opt-in. This run does not show a live throughput improvement, and synthetic signals cannot establish the quality cost of intentionally skipped windows. The independent hand-labeled audio A/B remains pending; physical-camera validation also remains open. No 5x profile is accepted as sustained real-time processing.

Raw JSON: [`live_rtsp_adaptive_2m_threads4_20261026/report.json`](live_rtsp_adaptive_2m_threads4_20261026/report.json). Standard comparison: [`live_rtsp_default_2m_threads4_20261026/report.json`](live_rtsp_default_2m_threads4_20261026/report.json). The broader default/window/thread comparison is summarized in [`live_rtsp_soak_2m_20261026.md`](live_rtsp_soak_2m_20261026.md).
