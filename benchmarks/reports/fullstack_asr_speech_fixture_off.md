# SHSD full-stack concurrent A/V benchmark

Generated: `2026-10-26T00:32:56.612513+00:00`

## Machine and workload

- CPU: AMD Ryzen 9 9900X3D 12-Core Processor
- OS / Python: Windows-11-10.0.26200-SP0 / 3.14.6
- Cores: 12 physical, 24 logical
- Input: `X:\AI\SHSD\tests\fixtures\media\audio_speech_ru.wav` (5016 ms)
- Levels / threads per stream: L0,L1 / 4
- Prefetch: `block`; capacity: default
- GigaAM ASR: off; L3 narrator: `qwen`
- Iterative text hypothesis axis: `off`
- SHSD: `shsd 0.1.0`; model revisions: {'embeddinggemma2': '914f7f89142e33e77833254d9c9b90c3cef7303b'}

Measurements are local file replay. Aggregate process CPU is reported as core equivalents and as a share of logical-core capacity. Timeline watermark backlog is used for L1/L2/L3 lag. Disk queue depth uses the Windows PhysicalDisk PDH counter when available; token throughput uses llama.cpp generation timings.

## Scale results

| Streams | Status | Cycles | Wall s | Processed media s | Aggregate RTF | Mean CPU cores | Peak RSS MiB | Disk queue p95/max | Tokens/s | Coverage misses / L2 rejects | L1 p50/p95 ms | L2 p50/p95 ms | L3 p50/p95 ms |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| 2 | passed | 1 | 16.4 | 10.0 | 1.6312 | 1.89 | 4029 | 0.0/1.0 | — | 0 / 0 | 2043.0/5016.0 | — | — |
| 5 | passed | 1 | 19.0 | 25.1 | 0.7579 | 4.61 | 10091 | 0.0/0.0 | — | 0 / 0 | 2043.0/5016.0 | — | — |

## Run details

### 2 concurrent streams

CPU capacity mean: 7.9%; peak aggregate process-tree RSS: 4029 MiB; disk queue p95/max: 0.0/1.0 over 124 samples; Qwen generation: — tokens/s over 0 measurements; L3 latency p50/p95: None/None ms; backends: {}; fallback reasons: {}; unsupported-claim count: 0; completed stream cycles: 2.

- Cycle 1, stream 1: passed, 16.2s, RTF 3.2386, C/E/R=5016/5016/{'L1': 5016, 'L2': 5016, 'L3': 5016}, matches 8, prefetch drops 0, log `benchmarks\reports\fullstack_asr_speech_fixture_off_runs\2x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 16.2s, RTF 3.2378, C/E/R=5016/5016/{'L1': 5016, 'L2': 5016, 'L3': 5016}, matches 8, prefetch drops 0, log `benchmarks\reports\fullstack_asr_speech_fixture_off_runs\2x\cycle-0001\stream-02\process.log`.

### 5 concurrent streams

CPU capacity mean: 19.2%; peak aggregate process-tree RSS: 10091 MiB; disk queue p95/max: 0.0/0.0 over 99 samples; Qwen generation: — tokens/s over 0 measurements; L3 latency p50/p95: None/None ms; backends: {}; fallback reasons: {}; unsupported-claim count: 0; completed stream cycles: 5.

- Cycle 1, stream 1: passed, 19.0s, RTF 3.7813, C/E/R=5016/5016/{'L1': 5016, 'L2': 5016, 'L3': 5016}, matches 8, prefetch drops 0, log `benchmarks\reports\fullstack_asr_speech_fixture_off_runs\5x\cycle-0001\stream-01\process.log`.
- Cycle 1, stream 2: passed, 19.0s, RTF 3.7805, C/E/R=5016/5016/{'L1': 5016, 'L2': 5016, 'L3': 5016}, matches 8, prefetch drops 0, log `benchmarks\reports\fullstack_asr_speech_fixture_off_runs\5x\cycle-0001\stream-02\process.log`.
- Cycle 1, stream 3: passed, 19.0s, RTF 3.7795, C/E/R=5016/5016/{'L1': 5016, 'L2': 5016, 'L3': 5016}, matches 8, prefetch drops 0, log `benchmarks\reports\fullstack_asr_speech_fixture_off_runs\5x\cycle-0001\stream-03\process.log`.
- Cycle 1, stream 4: passed, 19.0s, RTF 3.7789, C/E/R=5016/5016/{'L1': 5016, 'L2': 5016, 'L3': 5016}, matches 8, prefetch drops 0, log `benchmarks\reports\fullstack_asr_speech_fixture_off_runs\5x\cycle-0001\stream-04\process.log`.
- Cycle 1, stream 5: passed, 19.0s, RTF 3.7781, C/E/R=5016/5016/{'L1': 5016, 'L2': 5016, 'L3': 5016}, matches 8, prefetch drops 0, log `benchmarks\reports\fullstack_asr_speech_fixture_off_runs\5x\cycle-0001\stream-05\process.log`.

## Scope

Short `--cycles 1` runs are concurrency smoke measurements, not endurance-soak completion. Use `--duration-minutes 1`, `5`, `10`, or `30` to keep replaying the fixture at the selected concurrency for the requested wall time. Each cycle is a fresh CLI process and incurs process/model startup cost; embedding caches persist within a run directory. Token throughput is the measured llama.cpp generation rate; it is unavailable when L3 is off or timing output is absent.
