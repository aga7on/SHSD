# SHSD full-stack concurrent A/V benchmark

Generated: `2026-10-26T00:35:22.289426+00:00`

## Machine and workload

- CPU: AMD Ryzen 9 9900X3D 12-Core Processor
- OS / Python: Windows-11-10.0.26200-SP0 / 3.14.6
- Cores: 12 physical, 24 logical
- Input: `X:\AI\SHSD\tests\fixtures\media\av_sync_20s.mp4` (20000 ms)
- Levels / threads per stream: L0,L1 / 4
- Prefetch: `block`; capacity: default
- GigaAM ASR: off; L3 narrator: `qwen`
- Iterative text hypothesis axis: `off`
- SHSD: `shsd 0.1.0`; model revisions: {'embeddinggemma2': '914f7f89142e33e77833254d9c9b90c3cef7303b'}

Measurements are local file replay. Aggregate process CPU is reported as core equivalents and as a share of logical-core capacity. Timeline watermark backlog is used for L1/L2/L3 lag. Disk queue depth uses the Windows PhysicalDisk PDH counter when available; token throughput uses llama.cpp generation timings.

## Scale results

| Streams | Status | Cycles | Wall s | Processed media s | Aggregate RTF | Mean CPU cores | Peak RSS MiB | Disk queue p95/max | Tokens/s | Coverage misses / L2 rejects | L1 p50/p95 ms | L2 p50/p95 ms | L3 p50/p95 ms |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| 2 | passed | 1 | 17.4 | 40.0 | 0.4341 | 1.91 | 4681 | 0.0/1.0 | — | 0 / 0 | 10000.0/20000.0 | — | — |
| 5 | passed | 1 | 19.8 | 100.0 | 0.1977 | 4.76 | 11665 | 0.0/1.0 | — | 0 / 0 | 10000.0/20000.0 | — | — |

## Run details

### 2 concurrent streams

CPU capacity mean: 8.0%; peak aggregate process-tree RSS: 4681 MiB; disk queue p95/max: 0.0/1.0 over 131 samples; Qwen generation: — tokens/s over 0 measurements; L3 latency p50/p95: None/None ms; backends: {}; fallback reasons: {}; unsupported-claim count: 0; hypothesis iterations: 0; generated candidates: []; dynamic selections: 0; completed stream cycles: 2.

- Cycle 1, stream 1: passed, 17.2s, RTF 0.8618, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_hypothesis_baseline_1cycle_runs\2x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 17.3s, RTF 0.8666, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_hypothesis_baseline_1cycle_runs\2x\cycle-0001\stream-02\process.log`.

### 5 concurrent streams

CPU capacity mean: 19.9%; peak aggregate process-tree RSS: 11665 MiB; disk queue p95/max: 0.0/1.0 over 105 samples; Qwen generation: — tokens/s over 0 measurements; L3 latency p50/p95: None/None ms; backends: {}; fallback reasons: {}; unsupported-claim count: 0; hypothesis iterations: 0; generated candidates: []; dynamic selections: 0; completed stream cycles: 5.

- Cycle 1, stream 1: passed, 19.6s, RTF 0.9807, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_hypothesis_baseline_1cycle_runs\5x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 19.6s, RTF 0.9806, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_hypothesis_baseline_1cycle_runs\5x\cycle-0001\stream-02\process.log`.
- Cycle 1, stream 3: passed, 19.6s, RTF 0.9804, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_hypothesis_baseline_1cycle_runs\5x\cycle-0001\stream-03\process.log`.
- Cycle 1, stream 4: passed, 19.5s, RTF 0.9745, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_hypothesis_baseline_1cycle_runs\5x\cycle-0001\stream-04\process.log`.
- Cycle 1, stream 5: passed, 19.5s, RTF 0.9742, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `benchmarks\reports\fullstack_hypothesis_baseline_1cycle_runs\5x\cycle-0001\stream-05\process.log`.

## Scope

Short `--cycles 1` runs are concurrency smoke measurements, not endurance-soak completion. Use `--duration-minutes 1`, `5`, `10`, or `30` to keep replaying the fixture at the selected concurrency for the requested wall time. Each cycle is a fresh CLI process and incurs process/model startup cost; embedding caches persist within a run directory. Token throughput is the measured llama.cpp generation rate; it is unavailable when L3 is off or timing output is absent.
