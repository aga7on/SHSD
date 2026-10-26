# SHSD full-stack concurrent A/V benchmark

Generated: `2026-10-25T23:43:55.928862+00:00`

## Machine and workload

- CPU: AMD Ryzen 9 9900X3D 12-Core Processor
- OS / Python: Windows-11-10.0.26200-SP0 / 3.14.6
- Cores: 12 physical, 24 logical
- Input: `X:\AI\SHSD\tests\fixtures\media\av_sync_20s.mp4` (20000 ms)
- Levels / threads per stream: L0,L1,L2 / 4
- Prefetch: `block`; capacity: default
- SHSD: `shsd 0.1.0`; model revision: `914f7f89142e33e77833254d9c9b90c3cef7303b`

Measurements are local file replay. Aggregate process CPU is reported as core equivalents and as a share of logical-core capacity. Timeline watermark backlog is used for L1/L2/L3 lag; disk queue depth is unavailable from this runner's portable sampler.

## Scale results

| Streams | Status | Cycles | Wall s | Processed media s | Aggregate RTF | Mean CPU cores | Peak aggregate RSS MiB | Missed coverage | L1 p50/p95 ms | L2 p50/p95 ms | L3 p50/p95 ms |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | failed | 11 | 173.0 | 400.0 | 0.4324 | 1.91 | 4689 | 0 | 10000.0/20000.0 | 10000.0/20000.0 | — |
| 5 | failed | 1 | 0.6 | 0.0 | — | 2.03 | 213 | 0 | — | — | — |

## Run details

### 2 concurrent streams

CPU capacity mean: 7.9%; peak aggregate process-tree RSS: 4689 MiB; completed stream cycles: 20.

- Cycle 1, stream 1: passed, 17.0s, RTF 0.8509, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 17.1s, RTF 0.8558, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0001\stream-02\process.log`.
- Cycle 2, stream 1: passed, 17.2s, RTF 0.8578, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0002\stream-01\process.log`.
- Cycle 2, stream 2: passed, 17.1s, RTF 0.8525, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0002\stream-02\process.log`.
- Cycle 3, stream 1: passed, 17.3s, RTF 0.8634, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0003\stream-01\process.log`.
- Cycle 3, stream 2: passed, 17.2s, RTF 0.8582, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0003\stream-02\process.log`.
- Cycle 4, stream 1: passed, 17.2s, RTF 0.8589, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0004\stream-01\process.log`.
- Cycle 4, stream 2: passed, 17.2s, RTF 0.8586, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0004\stream-02\process.log`.
- Cycle 5, stream 1: passed, 17.0s, RTF 0.8482, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0005\stream-01\process.log`.
- Cycle 5, stream 2: passed, 17.0s, RTF 0.848, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0005\stream-02\process.log`.
- Cycle 6, stream 1: passed, 17.2s, RTF 0.8616, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0006\stream-01\process.log`.
- Cycle 6, stream 2: passed, 17.2s, RTF 0.8614, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0006\stream-02\process.log`.
- Cycle 7, stream 1: passed, 17.3s, RTF 0.866, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0007\stream-01\process.log`.
- Cycle 7, stream 2: passed, 17.4s, RTF 0.8709, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0007\stream-02\process.log`.
- Cycle 8, stream 1: passed, 17.3s, RTF 0.8626, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0008\stream-01\process.log`.
- Cycle 8, stream 2: passed, 17.2s, RTF 0.8623, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0008\stream-02\process.log`.
- Cycle 9, stream 1: passed, 17.2s, RTF 0.862, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0009\stream-01\process.log`.
- Cycle 9, stream 2: passed, 17.2s, RTF 0.8618, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0009\stream-02\process.log`.
- Cycle 10, stream 1: passed, 17.2s, RTF 0.8614, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0010\stream-01\process.log`.
- Cycle 10, stream 2: passed, 17.2s, RTF 0.8613, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0010\stream-02\process.log`.
- Cycle 11, stream 1: failed, 0.4s, RTF None, C/E/R=None/None/{}, matches —, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0011\stream-01\process.log`.
- Cycle 11, stream 2: failed, 0.4s, RTF None, C/E/R=None/None/{}, matches —, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\2x\cycle-0011\stream-02\process.log`.

### 5 concurrent streams

CPU capacity mean: 8.5%; peak aggregate process-tree RSS: 213 MiB; completed stream cycles: 0.

- Cycle 1, stream 1: failed, 0.4s, RTF None, C/E/R=None/None/{}, matches —, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\5x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: failed, 0.4s, RTF None, C/E/R=None/None/{}, matches —, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\5x\cycle-0001\stream-02\process.log`.
- Cycle 1, stream 3: failed, 0.4s, RTF None, C/E/R=None/None/{}, matches —, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\5x\cycle-0001\stream-03\process.log`.
- Cycle 1, stream 4: failed, 0.4s, RTF None, C/E/R=None/None/{}, matches —, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\5x\cycle-0001\stream-04\process.log`.
- Cycle 1, stream 5: failed, 0.4s, RTF None, C/E/R=None/None/{}, matches —, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_runs\5x\cycle-0001\stream-05\process.log`.

## Scope

Short `--cycles 1` runs are concurrency smoke measurements, not endurance-soak completion. Use `--duration-minutes 1`, `5`, `10`, or `30` to keep replaying the fixture at the selected concurrency for the requested wall time. Each cycle is a fresh CLI process and incurs process/model startup cost; embedding caches persist within a run directory.
