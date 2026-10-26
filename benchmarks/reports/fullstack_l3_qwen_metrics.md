# SHSD full-stack concurrent A/V benchmark

Generated: `2026-10-26T00:31:01.152115+00:00`

## Machine and workload

- CPU: AMD Ryzen 9 9900X3D 12-Core Processor
- OS / Python: Windows-11-10.0.26200-SP0 / 3.14.6
- Cores: 12 physical, 24 logical
- Input: `X:\AI\SHSD\tests\fixtures\media\av_sync_20s.mp4` (20000 ms)
- Levels / threads per stream: L0,L1,L2,L3 / 4
- Prefetch: `block`; capacity: default
- GigaAM ASR: off; L3 narrator: `qwen`
- Iterative text hypothesis axis: `off`
- SHSD: `shsd 0.1.0`; model revisions: {'embeddinggemma2': '914f7f89142e33e77833254d9c9b90c3cef7303b', 'qwen3_0_6b': '13ac06624948e4d8589cb4b6f90100837342fcb8'}

Measurements are local file replay. Aggregate process CPU is reported as core equivalents and as a share of logical-core capacity. Timeline watermark backlog is used for L1/L2/L3 lag. Disk queue depth uses the Windows PhysicalDisk PDH counter when available; token throughput uses llama.cpp generation timings.

## Scale results

| Streams | Status | Cycles | Wall s | Processed media s | Aggregate RTF | Mean CPU cores | Peak RSS MiB | Disk queue p95/max | Tokens/s | Coverage misses / L2 rejects | L1 p50/p95 ms | L2 p50/p95 ms | L3 p50/p95 ms |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| 2 | passed | 1 | 26.1 | 40.0 | 0.6529 | 3.52 | 6246 | 0.0/1.0 | 30.875 | 0 / 0 | 10000.0/20000.0 | 10000.0/20000.0 | 10000.0/20000.0 |
| 5 | passed | 1 | 34.2 | 100.0 | 0.3424 | 9.25 | 15608 | 0.0/2.0 | 12.3 | 0 / 0 | 10000.0/20000.0 | 10000.0/20000.0 | 10000.0/20000.0 |

## Run details

### 2 concurrent streams

CPU capacity mean: 14.7%; peak aggregate process-tree RSS: 6246 MiB; disk queue p95/max: 0.0/1.0 over 196 samples; Qwen generation: 12.3 tokens/s over 4 measurements; L3 latency p50/p95: 3466.065/4483.56 ms; backends: {'qwen': 4}; unsupported-claim count: 0; completed stream cycles: 2.

- Cycle 1, stream 1: passed, 25.8s, RTF 1.2877, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_l3_qwen_metrics_runs\2x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 26.0s, RTF 1.2986, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_l3_qwen_metrics_runs\2x\cycle-0001\stream-02\process.log`.

### 5 concurrent streams

CPU capacity mean: 38.5%; peak aggregate process-tree RSS: 15608 MiB; disk queue p95/max: 0.0/2.0 over 170 samples; Qwen generation: 12.3 tokens/s over 10 measurements; L3 latency p50/p95: 5778.728/7397.769 ms; backends: {'qwen': 10}; unsupported-claim count: 0; completed stream cycles: 5.

- Cycle 1, stream 1: passed, 34.1s, RTF 1.704, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_l3_qwen_metrics_runs\5x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 34.1s, RTF 1.7038, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_l3_qwen_metrics_runs\5x\cycle-0001\stream-02\process.log`.
- Cycle 1, stream 3: passed, 34.1s, RTF 1.7035, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_l3_qwen_metrics_runs\5x\cycle-0001\stream-03\process.log`.
- Cycle 1, stream 4: passed, 34.2s, RTF 1.7084, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_l3_qwen_metrics_runs\5x\cycle-0001\stream-04\process.log`.
- Cycle 1, stream 5: passed, 34.2s, RTF 1.7082, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_l3_qwen_metrics_runs\5x\cycle-0001\stream-05\process.log`.

## Scope

Short `--cycles 1` runs are concurrency smoke measurements, not endurance-soak completion. Use `--duration-minutes 1`, `5`, `10`, or `30` to keep replaying the fixture at the selected concurrency for the requested wall time. Each cycle is a fresh CLI process and incurs process/model startup cost; embedding caches persist within a run directory. Token throughput is the measured llama.cpp generation rate; it is unavailable when L3 is off or timing output is absent.
