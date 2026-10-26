# SHSD full-stack concurrent A/V benchmark

Generated: `2026-10-26T02:09:50.162090+00:00`

## Machine and workload

- CPU: AMD Ryzen 9 9900X3D 12-Core Processor
- OS / Python: Windows-11-10.0.26200-SP0 / 3.14.6
- Cores: 12 physical, 24 logical
- Input: `X:\AI\SHSD\tests\fixtures\media\av_sync_20s.mp4` (20000 ms)
- Levels / threads per stream: L0,L1,L2 / 4
- Prefetch: `block`; capacity: default
- Embedding cache: isolated per stream/cycle
- GigaAM ASR: off; L3 narrator: `qwen`
- Iterative text hypothesis axis: `off`
- SHSD: `shsd 0.1.0`; model revisions: {'embeddinggemma2': '914f7f89142e33e77833254d9c9b90c3cef7303b'}

Measurements are local file replay. Aggregate process CPU is reported as core equivalents and as a share of logical-core capacity. Timeline watermark backlog is used for L1/L2/L3 lag. Disk queue depth uses the Windows PhysicalDisk PDH counter when available; token throughput uses llama.cpp generation timings.

## Scale results

| Streams | Status | Cycles | Wall s | Processed media s | Aggregate RTF | Mean CPU cores | Peak RSS MiB | Disk queue p95/max | Tokens/s | Coverage misses / L2 rejects | L1 p50/p95 ms | L2 p50/p95 ms | L3 p50/p95 ms |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| 2 | passed | 1 | 35.5 | 40.0 | 0.8863 | 5.55 | 4740 | 0.0/1.0 | — | 0 / 0 | 10027.0/20000.0 | 10027.0/20000.0 | — |
| 5 | passed | 1 | 40.7 | 100.0 | 0.4072 | 13.28 | 11792 | 0.0/1.0 | — | 0 / 70 | 10027.0/20000.0 | 10027.0/20000.0 | — |

## Run details

### 2 concurrent streams

CPU capacity mean: 23.1%; peak aggregate process-tree RSS: 4740 MiB; disk queue p95/max: 0.0/1.0 over 266 samples; Qwen generation: — tokens/s over 0 measurements; L3 latency p50/p95: None/None ms; backends: {}; fallback reasons: {}; unsupported-claim count: 0; hypothesis iterations: 0; hypothesis errors: {}; generated candidates: []; dynamic selections: 0; completed stream cycles: 2.

- Cycle 1, stream 1: passed, 35.4s, RTF 1.7714, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_cold_cache\2x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 35.2s, RTF 1.7604, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_cold_cache\2x\cycle-0001\stream-02\process.log`.

### 5 concurrent streams

CPU capacity mean: 55.3%; peak aggregate process-tree RSS: 11792 MiB; disk queue p95/max: 0.0/1.0 over 213 samples; Qwen generation: — tokens/s over 0 measurements; L3 latency p50/p95: None/None ms; backends: {}; fallback reasons: {}; unsupported-claim count: 0; hypothesis iterations: 0; hypothesis errors: {}; generated candidates: []; dynamic selections: 0; completed stream cycles: 5.

- Cycle 1, stream 1: passed, 40.4s, RTF 2.0224, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_cold_cache\5x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 40.2s, RTF 2.0079, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_cold_cache\5x\cycle-0001\stream-02\process.log`.
- Cycle 1, stream 3: passed, 40.3s, RTF 2.0161, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_cold_cache\5x\cycle-0001\stream-03\process.log`.
- Cycle 1, stream 4: passed, 40.4s, RTF 2.0217, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_cold_cache\5x\cycle-0001\stream-04\process.log`.
- Cycle 1, stream 5: passed, 40.5s, RTF 2.0273, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_cold_cache\5x\cycle-0001\stream-05\process.log`.

## Scope

Short `--cycles 1` runs are concurrency smoke measurements, not endurance-soak completion. Use `--duration-minutes 1`, `5`, `10`, or `30` to keep replaying the fixture at the selected concurrency for the requested wall time. Each cycle is a fresh CLI process and incurs process/model startup cost. By default, embedding caches are shared; `--isolated-cache` creates a separate cache per stream and cycle to measure cold media inference. Token throughput is the measured llama.cpp generation rate; it is unavailable when L3 is off or timing output is absent.
