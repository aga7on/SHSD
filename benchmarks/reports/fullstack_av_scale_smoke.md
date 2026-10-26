# SHSD full-stack concurrent A/V benchmark

Generated: `2026-10-25T23:32:08.575493+00:00`

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
| 2 | passed | 1 | 17.2 | 40.0 | 0.4312 | 1.91 | 4670 | 0 | 10000.0/20000.0 | 10000.0/20000.0 | — |
| 5 | passed | 1 | 20.0 | 100.0 | 0.2001 | 4.73 | 11676 | 0 | 10000.0/20000.0 | 10000.0/20000.0 | — |

## Run details

### 2 concurrent streams

CPU capacity mean: 8.0%; peak aggregate process-tree RSS: 4670 MiB; completed stream cycles: 2.

- Cycle 1, stream 1: passed, 17.2s, RTF 0.8614, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_scale_smoke_runs\2x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 17.1s, RTF 0.8562, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_scale_smoke_runs\2x\cycle-0001\stream-02\process.log`.

### 5 concurrent streams

CPU capacity mean: 19.7%; peak aggregate process-tree RSS: 11676 MiB; completed stream cycles: 5.

- Cycle 1, stream 1: passed, 19.9s, RTF 0.9925, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_scale_smoke_runs\5x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 19.8s, RTF 0.9924, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_scale_smoke_runs\5x\cycle-0001\stream-02\process.log`.
- Cycle 1, stream 3: passed, 19.8s, RTF 0.9922, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_scale_smoke_runs\5x\cycle-0001\stream-03\process.log`.
- Cycle 1, stream 4: passed, 19.8s, RTF 0.9912, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_scale_smoke_runs\5x\cycle-0001\stream-04\process.log`.
- Cycle 1, stream 5: passed, 19.8s, RTF 0.9911, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_av_scale_smoke_runs\5x\cycle-0001\stream-05\process.log`.

## Scope

Short `--cycles 1` runs are concurrency smoke measurements, not endurance-soak completion. Use `--duration-minutes 1`, `5`, `10`, or `30` to keep replaying the fixture at the selected concurrency for the requested wall time. Each cycle is a fresh CLI process and incurs process/model startup cost; embedding caches persist within a run directory.
