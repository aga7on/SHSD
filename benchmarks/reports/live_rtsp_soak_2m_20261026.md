# Two-minute live RTSP soak: default and tuning controls

Date: 2026-10-26. Three isolated 120-second local RTSP runs exercised 2x and 5x synthetic A/V sources on the Ryzen 9 9900X3D. All used compact vision, a fresh embedding cache, and a 4 GiB memory limit. The runs compare the current four-thread / 5-second default, four threads / 10-second windows, and twelve threads / 5-second windows. Every scenario reached capture-ready and every source ended in `stopped`; no stream reported an error. Peak process-tree RSS stayed between 2.32 and 2.37 GiB.

RTF is the per-stream `end_to_end_elapsed` divided by final captured media seconds. Lag bands are median L1 lag across samples in each chronological quarter of the 120-second live interval. Final R/L1 issue spans sum typed `gap` and `skipped` intervals; a final watermark reaching C does not imply those intervals were analyzed.

## Five-source 5x results

| Threads / window | RTF median / max | L1 lag median by quarter | Peak L1 lag | Prefetch drops / scheduler rejects | Final R/L1 issue spans | Completed audio / image embeddings |
|---|---:|---:|---:|---:|---:|---:|
| 4 / 5 s | 1.065 / 1.087 | 6.1 → 23.9 → 47.1 → 55.1 s | 56.8 s | 11,360 / 63 | 527.9 / 646.0 s (81.7%) | 18 / 6 |
| 4 / 10 s | 1.078 / 1.096 | 11.8 → 34.9 → 50.5 → 55.8 s | 64.3 s | 10,902 / 43 | 549.0 / 639.0 s (85.9%) | 7 / 2 |
| 12 / 5 s | 1.117 / 1.120 | 6.8 → 24.5 → 36.2 → 39.8 s | 45.5 s | 10,517 / 42 | 576.1 / 642.6 s (89.6%) | 10 / 4 |

The 4-thread / 5-second default keeps more R/L1 intervals analyzed than either tuning control, but its lag rises through the soak. Twelve threads slow that rise, while leaving more R/L1 intervals uncovered. Doubling the window does not help: it yields fewer completed embeddings, higher peak lag, and more final R/L1 issue spans. No tested profile establishes sustained 5x real-time processing.

The default 5x run stayed within the configured 4 GiB limit (2.35 GiB peak process-tree RSS); four of five per-source load reports ended in `critical` with queue pressure, and the fifth ended `normal`. The 2x run ended with both sources `normal` and 2.32 GiB peak process-tree RSS. Capture-ring drops remained zero; the separately bounded shared prefetch queue reported the drops shown above.

## Two-source 2x results

| Threads / window | RTF median / max | Peak observed L1 lag | Prefetch drops / scheduler rejects | Final R/L1 issue spans |
|---|---:|---:|---:|---:|
| 4 / 5 s | 1.139 / 1.141 | 5.9 s | 282 / 86 | 0.7 / 250.9 s (0.3%) |
| 4 / 10 s | 1.147 / 1.154 | 12.7 s | 463 / 53 | 11.9 / 255.4 s (4.7%) |
| 12 / 5 s | 1.136 / 1.137 | 5.9 s | 173 / 139 | 8.0 / 259.1 s (3.1%) |

The four-thread / 5-second profile retained the lowest 2x lag and fewest final L1 issue spans. The measured RTF includes the live startup/drain interval and remained above 1 in all three runs.

## Decision and limits

Keep the four-thread / 5-second default. Increasing the window or thread count trades temporal coverage against queue lag and does not produce a sustainable 5x profile. The synthetic publishers measure scheduling and capacity; their signal and scene patterns do not establish semantic recall or replace physical-camera validation.

## Raw artifacts

- 4 threads / 5 s: [`live_rtsp_default_2m_threads4_20261026/report.json`](live_rtsp_default_2m_threads4_20261026/report.json)
- 4 threads / 10 s: [`live_rtsp_window10s_2m_threads4_20261026/report.json`](live_rtsp_window10s_2m_threads4_20261026/report.json)
- 12 threads / 5 s: [`live_rtsp_default_2m_threads12_20261026/report.json`](live_rtsp_default_2m_threads12_20261026/report.json)
- Earlier 60-second sweep: [`live_rtsp_thread_sweep_60s_20261026.md`](live_rtsp_thread_sweep_60s_20261026.md)
