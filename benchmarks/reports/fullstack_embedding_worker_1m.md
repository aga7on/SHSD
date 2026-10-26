# SHSD full-stack concurrent A/V benchmark

Generated: `2026-10-26T02:06:08.464605+00:00`

## Machine and workload

- CPU: AMD Ryzen 9 9900X3D 12-Core Processor
- OS / Python: Windows-11-10.0.26200-SP0 / 3.14.6
- Cores: 12 physical, 24 logical
- Input: `X:\AI\SHSD\tests\fixtures\media\av_sync_20s.mp4` (20000 ms)
- Levels / threads per stream: L0,L1,L2 / 4
- Prefetch: `block`; capacity: default
- GigaAM ASR: off; L3 narrator: `qwen`
- Iterative text hypothesis axis: `off`
- SHSD: `shsd 0.1.0`; model revisions: {'embeddinggemma2': '914f7f89142e33e77833254d9c9b90c3cef7303b'}

Measurements are local file replay. Aggregate process CPU is reported as core equivalents and as a share of logical-core capacity. Timeline watermark backlog is used for L1/L2/L3 lag. Disk queue depth uses the Windows PhysicalDisk PDH counter when available; token throughput uses llama.cpp generation timings.

## Scale results

| Streams | Status | Cycles | Wall s | Processed media s | Aggregate RTF | Mean CPU cores | Peak RSS MiB | Disk queue p95/max | Tokens/s | Coverage misses / L2 rejects | L1 p50/p95 ms | L2 p50/p95 ms | L3 p50/p95 ms |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| 2 | passed | 4 | 64.2 | 160.0 | 0.4014 | 1.95 | 4676 | 0.0/1.0 | — | 0 / 0 | 10000.0/20000.0 | 10000.0/20000.0 | — |
| 5 | passed | 4 | 73.6 | 400.0 | 0.184 | 4.80 | 11695 | 0.0/1.0 | — | 0 / 0 | 10000.0/20000.0 | 10000.0/20000.0 | — |

## Run details

### 2 concurrent streams

CPU capacity mean: 8.1%; peak aggregate process-tree RSS: 4676 MiB; disk queue p95/max: 0.0/1.0 over 485 samples; Qwen generation: — tokens/s over 0 measurements; L3 latency p50/p95: None/None ms; backends: {}; fallback reasons: {}; unsupported-claim count: 0; hypothesis iterations: 0; hypothesis errors: {}; generated candidates: []; dynamic selections: 0; completed stream cycles: 8.

- Cycle 1, stream 1: passed, 16.2s, RTF 0.8084, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\2x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 16.2s, RTF 0.8082, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\2x\cycle-0001\stream-02\process.log`.
- Cycle 2, stream 1: passed, 16.0s, RTF 0.802, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\2x\cycle-0002\stream-01\process.log`.
- Cycle 2, stream 2: passed, 16.0s, RTF 0.8017, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\2x\cycle-0002\stream-02\process.log`.
- Cycle 3, stream 1: passed, 16.0s, RTF 0.7981, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\2x\cycle-0003\stream-01\process.log`.
- Cycle 3, stream 2: passed, 16.0s, RTF 0.7979, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\2x\cycle-0003\stream-02\process.log`.
- Cycle 4, stream 1: passed, 15.9s, RTF 0.7974, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\2x\cycle-0004\stream-01\process.log`.
- Cycle 4, stream 2: passed, 15.8s, RTF 0.7922, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\2x\cycle-0004\stream-02\process.log`.

### 5 concurrent streams

CPU capacity mean: 20.0%; peak aggregate process-tree RSS: 11695 MiB; disk queue p95/max: 0.0/1.0 over 387 samples; Qwen generation: — tokens/s over 0 measurements; L3 latency p50/p95: None/None ms; backends: {}; fallback reasons: {}; unsupported-claim count: 0; hypothesis iterations: 0; hypothesis errors: {}; generated candidates: []; dynamic selections: 0; completed stream cycles: 20.

- Cycle 1, stream 1: passed, 18.5s, RTF 0.9233, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 18.4s, RTF 0.9182, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0001\stream-02\process.log`.
- Cycle 1, stream 3: passed, 18.5s, RTF 0.923, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0001\stream-03\process.log`.
- Cycle 1, stream 4: passed, 18.4s, RTF 0.9178, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0001\stream-04\process.log`.
- Cycle 1, stream 5: passed, 18.5s, RTF 0.9227, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0001\stream-05\process.log`.
- Cycle 2, stream 1: passed, 18.2s, RTF 0.9117, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0002\stream-01\process.log`.
- Cycle 2, stream 2: passed, 18.2s, RTF 0.9116, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0002\stream-02\process.log`.
- Cycle 2, stream 3: passed, 18.2s, RTF 0.9114, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0002\stream-03\process.log`.
- Cycle 2, stream 4: passed, 18.2s, RTF 0.9113, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0002\stream-04\process.log`.
- Cycle 2, stream 5: passed, 18.2s, RTF 0.9111, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0002\stream-05\process.log`.
- Cycle 3, stream 1: passed, 18.2s, RTF 0.9089, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0003\stream-01\process.log`.
- Cycle 3, stream 2: passed, 18.3s, RTF 0.9137, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0003\stream-02\process.log`.
- Cycle 3, stream 3: passed, 18.2s, RTF 0.9085, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0003\stream-03\process.log`.
- Cycle 3, stream 4: passed, 18.2s, RTF 0.9084, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0003\stream-04\process.log`.
- Cycle 3, stream 5: passed, 18.2s, RTF 0.9082, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0003\stream-05\process.log`.
- Cycle 4, stream 1: passed, 18.3s, RTF 0.9156, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0004\stream-01\process.log`.
- Cycle 4, stream 2: passed, 18.4s, RTF 0.9204, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0004\stream-02\process.log`.
- Cycle 4, stream 3: passed, 18.4s, RTF 0.9203, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0004\stream-03\process.log`.
- Cycle 4, stream 4: passed, 18.4s, RTF 0.9201, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0004\stream-04\process.log`.
- Cycle 4, stream 5: passed, 18.4s, RTF 0.9198, C/E/R=20000/20000/{'L1': 20000, 'L2': 20000, 'L3': 20000}, matches 36, prefetch drops 0, log `runs\fullstack_embedding_worker_1m\5x\cycle-0004\stream-05\process.log`.

## Scope

Short `--cycles 1` runs are concurrency smoke measurements, not endurance-soak completion. Use `--duration-minutes 1`, `5`, `10`, or `30` to keep replaying the fixture at the selected concurrency for the requested wall time. Each cycle is a fresh CLI process and incurs process/model startup cost; embedding caches persist within a run directory. Token throughput is the measured llama.cpp generation rate; it is unavailable when L3 is off or timing output is absent.

This run used the shared default embedding cache. Each stream reported 9 completed jobs but only about 40 ms total encoding time, so the fixture embeddings were already cached. Treat this as a warm-cache process-scale check; it does not measure cold inference or isolate a speed effect from the embedding worker. The isolated-cache one-cycle comparison is in [`fullstack_embedding_worker_cold_cache.md`](fullstack_embedding_worker_cold_cache.md).
