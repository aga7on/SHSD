# SHSD full-stack concurrent A/V benchmark

Generated: `2026-10-25T23:50:44.477067+00:00`

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
| 2 | passed | 18 | 312.1 | 720.0 | 0.4334 | 1.91 | 4697 | 0 | 10000.0/20000.0 | 10000.0/20000.0 | — |
| 5 | passed | 16 | 316.1 | 1600.0 | 0.1976 | 4.75 | 11717 | 0 | 10000.0/20000.0 | 10000.0/20000.0 | — |

## Run details

### 2 concurrent streams

CPU capacity mean: 8.0%; peak aggregate process-tree RSS: 4697 MiB; completed stream cycles: 36.

- Cycle 1, stream 1: passed, 17.4s, RTF 0.8684, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 17.3s, RTF 0.8632, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0001\stream-02\process.log`.
- Cycle 2, stream 1: passed, 17.0s, RTF 0.8521, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0002\stream-01\process.log`.
- Cycle 2, stream 2: passed, 17.1s, RTF 0.8569, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0002\stream-02\process.log`.
- Cycle 3, stream 1: passed, 17.5s, RTF 0.8748, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0003\stream-01\process.log`.
- Cycle 3, stream 2: passed, 17.5s, RTF 0.8745, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0003\stream-02\process.log`.
- Cycle 4, stream 1: passed, 17.4s, RTF 0.8682, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0004\stream-01\process.log`.
- Cycle 4, stream 2: passed, 17.4s, RTF 0.868, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0004\stream-02\process.log`.
- Cycle 5, stream 1: passed, 17.2s, RTF 0.8622, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0005\stream-01\process.log`.
- Cycle 5, stream 2: passed, 17.2s, RTF 0.862, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0005\stream-02\process.log`.
- Cycle 6, stream 1: passed, 17.1s, RTF 0.8571, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0006\stream-01\process.log`.
- Cycle 6, stream 2: passed, 17.0s, RTF 0.8519, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0006\stream-02\process.log`.
- Cycle 7, stream 1: passed, 17.3s, RTF 0.8629, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0007\stream-01\process.log`.
- Cycle 7, stream 2: passed, 17.3s, RTF 0.8628, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0007\stream-02\process.log`.
- Cycle 8, stream 1: passed, 17.2s, RTF 0.8579, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0008\stream-01\process.log`.
- Cycle 8, stream 2: passed, 17.3s, RTF 0.8627, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0008\stream-02\process.log`.
- Cycle 9, stream 1: passed, 17.1s, RTF 0.8565, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0009\stream-01\process.log`.
- Cycle 9, stream 2: passed, 17.2s, RTF 0.8613, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0009\stream-02\process.log`.
- Cycle 10, stream 1: passed, 17.3s, RTF 0.8656, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0010\stream-01\process.log`.
- Cycle 10, stream 2: passed, 17.3s, RTF 0.8654, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0010\stream-02\process.log`.
- Cycle 11, stream 1: passed, 17.3s, RTF 0.866, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0011\stream-01\process.log`.
- Cycle 11, stream 2: passed, 17.3s, RTF 0.8658, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0011\stream-02\process.log`.
- Cycle 12, stream 1: passed, 17.2s, RTF 0.8599, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0012\stream-01\process.log`.
- Cycle 12, stream 2: passed, 17.2s, RTF 0.8597, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0012\stream-02\process.log`.
- Cycle 13, stream 1: passed, 17.7s, RTF 0.8835, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0013\stream-01\process.log`.
- Cycle 13, stream 2: passed, 17.6s, RTF 0.8784, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0013\stream-02\process.log`.
- Cycle 14, stream 1: passed, 17.5s, RTF 0.8733, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0014\stream-01\process.log`.
- Cycle 14, stream 2: passed, 17.5s, RTF 0.8732, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0014\stream-02\process.log`.
- Cycle 15, stream 1: passed, 17.2s, RTF 0.8594, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0015\stream-01\process.log`.
- Cycle 15, stream 2: passed, 17.1s, RTF 0.8542, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0015\stream-02\process.log`.
- Cycle 16, stream 1: passed, 17.6s, RTF 0.878, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0016\stream-01\process.log`.
- Cycle 16, stream 2: passed, 17.6s, RTF 0.8778, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0016\stream-02\process.log`.
- Cycle 17, stream 1: passed, 17.3s, RTF 0.8644, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0017\stream-01\process.log`.
- Cycle 17, stream 2: passed, 17.3s, RTF 0.8642, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0017\stream-02\process.log`.
- Cycle 18, stream 1: passed, 17.0s, RTF 0.8493, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0018\stream-01\process.log`.
- Cycle 18, stream 2: passed, 17.0s, RTF 0.8492, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\2x\cycle-0018\stream-02\process.log`.

### 5 concurrent streams

CPU capacity mean: 19.8%; peak aggregate process-tree RSS: 11717 MiB; completed stream cycles: 80.

- Cycle 1, stream 1: passed, 19.6s, RTF 0.9803, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 19.7s, RTF 0.9851, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0001\stream-02\process.log`.
- Cycle 1, stream 3: passed, 19.6s, RTF 0.9799, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0001\stream-03\process.log`.
- Cycle 1, stream 4: passed, 19.7s, RTF 0.9848, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0001\stream-04\process.log`.
- Cycle 1, stream 5: passed, 19.6s, RTF 0.9796, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0001\stream-05\process.log`.
- Cycle 2, stream 1: passed, 19.8s, RTF 0.9906, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0002\stream-01\process.log`.
- Cycle 2, stream 2: passed, 19.8s, RTF 0.9903, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0002\stream-02\process.log`.
- Cycle 2, stream 3: passed, 19.7s, RTF 0.9851, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0002\stream-03\process.log`.
- Cycle 2, stream 4: passed, 19.8s, RTF 0.9899, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0002\stream-04\process.log`.
- Cycle 2, stream 5: passed, 19.7s, RTF 0.9848, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0002\stream-05\process.log`.
- Cycle 3, stream 1: passed, 19.6s, RTF 0.9788, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0003\stream-01\process.log`.
- Cycle 3, stream 2: passed, 19.6s, RTF 0.9786, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0003\stream-02\process.log`.
- Cycle 3, stream 3: passed, 19.6s, RTF 0.9784, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0003\stream-03\process.log`.
- Cycle 3, stream 4: passed, 19.6s, RTF 0.9782, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0003\stream-04\process.log`.
- Cycle 3, stream 5: passed, 19.6s, RTF 0.978, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0003\stream-05\process.log`.
- Cycle 4, stream 1: passed, 19.5s, RTF 0.9755, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0004\stream-01\process.log`.
- Cycle 4, stream 2: passed, 19.5s, RTF 0.9754, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0004\stream-02\process.log`.
- Cycle 4, stream 3: passed, 19.6s, RTF 0.9802, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0004\stream-03\process.log`.
- Cycle 4, stream 4: passed, 19.5s, RTF 0.9749, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0004\stream-04\process.log`.
- Cycle 4, stream 5: passed, 19.5s, RTF 0.9747, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0004\stream-05\process.log`.
- Cycle 5, stream 1: passed, 19.7s, RTF 0.9839, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0005\stream-01\process.log`.
- Cycle 5, stream 2: passed, 19.7s, RTF 0.9838, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0005\stream-02\process.log`.
- Cycle 5, stream 3: passed, 19.8s, RTF 0.9886, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0005\stream-03\process.log`.
- Cycle 5, stream 4: passed, 19.8s, RTF 0.9884, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0005\stream-04\process.log`.
- Cycle 5, stream 5: passed, 19.8s, RTF 0.9883, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0005\stream-05\process.log`.
- Cycle 6, stream 1: passed, 19.7s, RTF 0.9858, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0006\stream-01\process.log`.
- Cycle 6, stream 2: passed, 19.6s, RTF 0.9806, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0006\stream-02\process.log`.
- Cycle 6, stream 3: passed, 19.6s, RTF 0.9805, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0006\stream-03\process.log`.
- Cycle 6, stream 4: passed, 19.6s, RTF 0.9803, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0006\stream-04\process.log`.
- Cycle 6, stream 5: passed, 19.6s, RTF 0.98, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0006\stream-05\process.log`.
- Cycle 7, stream 1: passed, 19.6s, RTF 0.9822, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0007\stream-01\process.log`.
- Cycle 7, stream 2: passed, 19.6s, RTF 0.9819, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0007\stream-02\process.log`.
- Cycle 7, stream 3: passed, 19.6s, RTF 0.9818, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0007\stream-03\process.log`.
- Cycle 7, stream 4: passed, 19.6s, RTF 0.9816, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0007\stream-04\process.log`.
- Cycle 7, stream 5: passed, 19.6s, RTF 0.9815, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0007\stream-05\process.log`.
- Cycle 8, stream 1: passed, 19.6s, RTF 0.9816, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0008\stream-01\process.log`.
- Cycle 8, stream 2: passed, 19.6s, RTF 0.9813, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0008\stream-02\process.log`.
- Cycle 8, stream 3: passed, 19.6s, RTF 0.9812, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0008\stream-03\process.log`.
- Cycle 8, stream 4: passed, 19.6s, RTF 0.981, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0008\stream-04\process.log`.
- Cycle 8, stream 5: passed, 19.7s, RTF 0.9858, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0008\stream-05\process.log`.
- Cycle 9, stream 1: passed, 19.7s, RTF 0.985, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0009\stream-01\process.log`.
- Cycle 9, stream 2: passed, 19.7s, RTF 0.9848, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0009\stream-02\process.log`.
- Cycle 9, stream 3: passed, 19.7s, RTF 0.9846, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0009\stream-03\process.log`.
- Cycle 9, stream 4: passed, 19.7s, RTF 0.9845, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0009\stream-04\process.log`.
- Cycle 9, stream 5: passed, 19.7s, RTF 0.9843, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0009\stream-05\process.log`.
- Cycle 10, stream 1: passed, 19.8s, RTF 0.9904, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0010\stream-01\process.log`.
- Cycle 10, stream 2: passed, 19.6s, RTF 0.9793, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0010\stream-02\process.log`.
- Cycle 10, stream 3: passed, 19.7s, RTF 0.985, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0010\stream-03\process.log`.
- Cycle 10, stream 4: passed, 19.6s, RTF 0.9789, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0010\stream-04\process.log`.
- Cycle 10, stream 5: passed, 19.6s, RTF 0.9788, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0010\stream-05\process.log`.
- Cycle 11, stream 1: passed, 19.8s, RTF 0.9889, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0011\stream-01\process.log`.
- Cycle 11, stream 2: passed, 19.8s, RTF 0.9887, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0011\stream-02\process.log`.
- Cycle 11, stream 3: passed, 19.8s, RTF 0.9885, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0011\stream-03\process.log`.
- Cycle 11, stream 4: passed, 19.8s, RTF 0.9883, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0011\stream-04\process.log`.
- Cycle 11, stream 5: passed, 19.7s, RTF 0.9831, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0011\stream-05\process.log`.
- Cycle 12, stream 1: passed, 19.6s, RTF 0.9799, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0012\stream-01\process.log`.
- Cycle 12, stream 2: passed, 19.6s, RTF 0.9798, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0012\stream-02\process.log`.
- Cycle 12, stream 3: passed, 19.5s, RTF 0.9746, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0012\stream-03\process.log`.
- Cycle 12, stream 4: passed, 19.6s, RTF 0.9794, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0012\stream-04\process.log`.
- Cycle 12, stream 5: passed, 19.6s, RTF 0.9793, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0012\stream-05\process.log`.
- Cycle 13, stream 1: passed, 19.4s, RTF 0.9695, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0013\stream-01\process.log`.
- Cycle 13, stream 2: passed, 19.5s, RTF 0.9743, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0013\stream-02\process.log`.
- Cycle 13, stream 3: passed, 19.5s, RTF 0.9742, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0013\stream-03\process.log`.
- Cycle 13, stream 4: passed, 19.4s, RTF 0.969, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0013\stream-04\process.log`.
- Cycle 13, stream 5: passed, 19.5s, RTF 0.9738, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0013\stream-05\process.log`.
- Cycle 14, stream 1: passed, 19.8s, RTF 0.9894, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0014\stream-01\process.log`.
- Cycle 14, stream 2: passed, 19.8s, RTF 0.9892, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0014\stream-02\process.log`.
- Cycle 14, stream 3: passed, 19.7s, RTF 0.9839, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0014\stream-03\process.log`.
- Cycle 14, stream 4: passed, 19.7s, RTF 0.9838, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0014\stream-04\process.log`.
- Cycle 14, stream 5: passed, 19.7s, RTF 0.9835, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0014\stream-05\process.log`.
- Cycle 15, stream 1: passed, 19.5s, RTF 0.9768, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0015\stream-01\process.log`.
- Cycle 15, stream 2: passed, 19.6s, RTF 0.9816, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0015\stream-02\process.log`.
- Cycle 15, stream 3: passed, 19.6s, RTF 0.9814, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0015\stream-03\process.log`.
- Cycle 15, stream 4: passed, 19.6s, RTF 0.9812, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0015\stream-04\process.log`.
- Cycle 15, stream 5: passed, 19.6s, RTF 0.981, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0015\stream-05\process.log`.
- Cycle 16, stream 1: passed, 19.6s, RTF 0.9799, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0016\stream-01\process.log`.
- Cycle 16, stream 2: passed, 19.6s, RTF 0.9797, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0016\stream-02\process.log`.
- Cycle 16, stream 3: passed, 19.6s, RTF 0.9795, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0016\stream-03\process.log`.
- Cycle 16, stream 4: passed, 19.6s, RTF 0.9793, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0016\stream-04\process.log`.
- Cycle 16, stream 5: passed, 19.6s, RTF 0.9792, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_5m_soak_retry_runs\5x\cycle-0016\stream-05\process.log`.

## Scope

Short `--cycles 1` runs are concurrency smoke measurements, not endurance-soak completion. Use `--duration-minutes 1`, `5`, `10`, or `30` to keep replaying the fixture at the selected concurrency for the requested wall time. Each cycle is a fresh CLI process and incurs process/model startup cost; embedding caches persist within a run directory.
