# SHSD full-stack concurrent A/V benchmark

Generated: `2026-10-25T23:34:22.751762+00:00`

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
| 2 | passed | 4 | 69.9 | 160.0 | 0.4366 | 1.91 | 4675 | 0 | 10000.0/20000.0 | 10000.0/20000.0 | — |
| 5 | passed | 4 | 79.4 | 400.0 | 0.1986 | 4.74 | 11682 | 0 | 10000.0/20000.0 | 10000.0/20000.0 | — |

## Run details

### 2 concurrent streams

CPU capacity mean: 8.0%; peak aggregate process-tree RSS: 4675 MiB; completed stream cycles: 8.

- Cycle 1, stream 1: passed, 17.3s, RTF 0.8648, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\2x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 17.3s, RTF 0.8645, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\2x\cycle-0001\stream-02\process.log`.
- Cycle 2, stream 1: passed, 17.3s, RTF 0.8653, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\2x\cycle-0002\stream-01\process.log`.
- Cycle 2, stream 2: passed, 17.2s, RTF 0.8601, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\2x\cycle-0002\stream-02\process.log`.
- Cycle 3, stream 1: passed, 17.5s, RTF 0.8754, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\2x\cycle-0003\stream-01\process.log`.
- Cycle 3, stream 2: passed, 17.5s, RTF 0.8752, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\2x\cycle-0003\stream-02\process.log`.
- Cycle 4, stream 1: passed, 17.6s, RTF 0.8818, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\2x\cycle-0004\stream-01\process.log`.
- Cycle 4, stream 2: passed, 17.5s, RTF 0.8767, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\2x\cycle-0004\stream-02\process.log`.

### 5 concurrent streams

CPU capacity mean: 19.8%; peak aggregate process-tree RSS: 11682 MiB; completed stream cycles: 20.

- Cycle 1, stream 1: passed, 19.7s, RTF 0.986, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 19.6s, RTF 0.9807, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0001\stream-02\process.log`.
- Cycle 1, stream 3: passed, 19.6s, RTF 0.9806, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0001\stream-03\process.log`.
- Cycle 1, stream 4: passed, 19.6s, RTF 0.9804, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0001\stream-04\process.log`.
- Cycle 1, stream 5: passed, 19.6s, RTF 0.9803, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0001\stream-05\process.log`.
- Cycle 2, stream 1: passed, 19.8s, RTF 0.9898, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0002\stream-01\process.log`.
- Cycle 2, stream 2: passed, 19.7s, RTF 0.9846, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0002\stream-02\process.log`.
- Cycle 2, stream 3: passed, 19.7s, RTF 0.9845, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0002\stream-03\process.log`.
- Cycle 2, stream 4: passed, 19.7s, RTF 0.9843, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0002\stream-04\process.log`.
- Cycle 2, stream 5: passed, 19.7s, RTF 0.9841, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0002\stream-05\process.log`.
- Cycle 3, stream 1: passed, 19.9s, RTF 0.9948, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0003\stream-01\process.log`.
- Cycle 3, stream 2: passed, 19.8s, RTF 0.9897, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0003\stream-02\process.log`.
- Cycle 3, stream 3: passed, 19.8s, RTF 0.9891, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0003\stream-03\process.log`.
- Cycle 3, stream 4: passed, 19.9s, RTF 0.994, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0003\stream-04\process.log`.
- Cycle 3, stream 5: passed, 19.8s, RTF 0.9887, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0003\stream-05\process.log`.
- Cycle 4, stream 1: passed, 19.8s, RTF 0.9896, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0004\stream-01\process.log`.
- Cycle 4, stream 2: passed, 19.8s, RTF 0.9895, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0004\stream-02\process.log`.
- Cycle 4, stream 3: passed, 19.7s, RTF 0.9843, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0004\stream-03\process.log`.
- Cycle 4, stream 4: passed, 19.8s, RTF 0.9892, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0004\stream-04\process.log`.
- Cycle 4, stream 5: passed, 19.7s, RTF 0.9839, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_1m_soak_runs\5x\cycle-0004\stream-05\process.log`.

## Scope

Short `--cycles 1` runs are concurrency smoke measurements, not endurance-soak completion. Use `--duration-minutes 1`, `5`, `10`, or `30` to keep replaying the fixture at the selected concurrency for the requested wall time. Each cycle is a fresh CLI process and incurs process/model startup cost; embedding caches persist within a run directory.
