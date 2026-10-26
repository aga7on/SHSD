# 60-second live CPU + Qwen latency check

## Setup

The 90-second *Tears of Steel* A/V excerpt was published through local RTSP with FFmpeg `-re` for 60.0 seconds. SHSD ran on CPU with four inference threads, five-second windows, standard vision sampling, L0/L1/L2/L3, and Qwen requested for L3. The host CPU was AMD Ryzen 9 9900X3D (12 cores / 24 logical CPUs). MediaMTX v1.21.2 was downloaded from the [official release](https://github.com/bluenviron/mediamtx/releases/tag/v1.21.2); the archive SHA-256 was verified as `a84224f5a490855684e62ba6fb71e80ea2a5e16aed61883bb58380290e93e467`.

Two runs used the same publisher duration and configuration: one cold EmbeddingGemma cache, then one warm embedding cache. Qwen remained enabled in both. Only outputs first observed while the publisher was running count as live. Event output lag uses event revision time minus source end time. Caption output lag uses the first 1-second API polling snapshot where the caption appeared, so it is an upper-bound estimate with up to one second of polling delay.

## Pre-stop progress and output lag

| Measure | Cold embedding cache | Warm embedding cache |
|---|---:|---:|
| Publisher duration | 60.000 s | 60.000 s |
| Last sampled capture C | 42.012 s | 43.015 s |
| Last sampled embedding E | 35.075 s | 40.015 s |
| Last sampled R[L1] | 35.075 s | 40.061 s |
| Last sampled R[L2] | 25.075 s | 25.061 s |
| Last sampled R[L3] | 29.887 s | 25.061 s |
| Live L1 event revisions | 26 | 30 |
| L1 output lag p50 / p95 / max | 21.145 / 30.942 / 30.947 s | 16.538 / 25.899 / 30.769 s |
| Live L2 event revisions | 12 | 15 |
| L2 output lag p50 / p95 / max | 16.572 / 16.580 / 16.580 s | 16.181 / 30.770 / 30.770 s |
| Live L3 captions | 2 | 4 |
| L3 first-observed lag p50 / p95 / max | 20.126 / 20.649 / 20.649 s | 19.014 / 19.323 / 19.323 s |

The first live caption appeared at 26.489 s in the cold run and 26.479 s in the warm run. The cold run's two live captions were one Qwen generation and one fallback. The warm run's four live captions were Qwen generations; all repeat a generic scene-change description. Nine additional captions in the warm run arrived only after the publisher stopped and are excluded from L3 live latency.

## Stop and final capture

Both publishers stopped at 60.0 seconds. Terminal analysis state arrived 79.879 seconds after start in the cold run and 79.776 seconds in the warm run, about 19.8 seconds after stop. Final capture C reached only 43.509 s and 43.865 s respectively; the remainder of the 60-second publisher interval had not been ingested. Post-stop drain completed analysis of captured media, but it does not count as live throughput.

## Result

The CPU/Qwen pipeline emitted L1, L2, and L3 output before stop, but did not sustain real-time source coverage: capture reached about 42–43 seconds during a 60-second publication, while R[L2] reached about 25 seconds. Live event and caption output remained roughly 16–31 seconds behind their source timestamps. Warm embedding cache improved some L1 latencies but did not make the stream real-time. Qwen's generated text remained generic and did not describe the dialogue or music. This one-times loopback test does not close F6.01; sustained 2x/5x acceptance and physical-camera validation remain open.

## Raw evidence

- Cold cache: `live_qwen_online_60s_20261026/report.json`, `events_live.json`, `captions_live.json`.
- Warm embedding cache: `live_qwen_online_60s_cache_recheck_20261026/report.json`, `events_live.json`, `captions_live.json`.
- Runner: `scripts/benchmark_live_qwen.py`.
