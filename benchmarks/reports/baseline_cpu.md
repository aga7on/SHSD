# SHSD CPU baseline

Generated: `2026-10-25T19:51:23.766625+00:00`

## Machine

- CPU: AMD Ryzen 9 9900X3D 12-Core Processor
- OS / Python: Windows-11-10.0.26200-SP0 / 3.14.6
- Cores: 12 physical, 24 logical
- ISA flags: avx, avx2, avx512bitalg, avx512bw, avx512cd, avx512dq, avx512f, avx512ifma, avx512vbmi, avx512vbmi2, avx512vl, avx512vnni, avx512vpopcntdq, sse, sse2, sse4_1, sse4_2, sse4a
- RAM: 95909 MiB
- Embedding model load: 11775.7 ms
- Embedding model load process-tree peak RSS: 2318 MiB

## EmbeddingGemma 2

Latency is CPU wall time per encode call. Repeated inputs use distinct cache keys; recorded cache hits are flagged.

| Threads | Audio | Mean ms | p50 ms | p95 ms |
|---:|---:|---:|---:|---:|
| 1 | 3s | 311.9 | 298.8 | 334.6 |
| 1 | 5s | 470.5 | 467.0 | 483.7 |
| 1 | 10s | 1031.9 | 1022.3 | 1056.8 |
| 2 | 3s | 257.3 | 265.0 | 287.7 |
| 2 | 5s | 306.0 | 306.4 | 310.2 |
| 2 | 10s | 630.6 | 596.4 | 754.3 |
| 4 | 3s | 201.6 | 197.5 | 210.9 |
| 4 | 5s | 276.9 | 274.6 | 281.0 |
| 4 | 10s | 483.7 | 480.2 | 490.7 |

### Other stages

| Threads | Text p50/p95 ms | Frame p50/p95 ms | Video p50/p95 ms | Joint AV p50/p95 ms | Top-k p50/p95 ms |
|---:|---:|---:|---:|---:|---:|
| 1 | 39.0/42.8 | 9722.9/10312.4 | 30036.2/30374.1 | 22664.7/23259.9 | 0.019/0.074 |
| 2 | 31.8/42.4 | 6977.7/7107.1 | 20783.2/21050.0 | 15848.9/16413.9 | 0.017/0.070 |
| 4 | 44.5/54.0 | 3909.0/3952.1 | 12837.4/13350.2 | 10251.0/10613.8 | 0.021/0.073 |

## Process scaling

Three-second audio windows run with one CPU thread in each worker.

| Processes | Tasks | Wall ms | Tasks/s | Task p50 ms | Peak process-tree RSS MiB |
|---:|---:|---:|---:|---:|---:|
| 1 | 3 | 14061.0 | 0.213 | 378.1 | 4532 |
| 2 | 6 | 14490.8 | 0.414 | 435.0 | 6534 |
| 4 | 12 | 16119.0 | 0.744 | 468.5 | 10548 |

## Measured workload notes

At 4 threads, the slowest measured stage was 8-second video embedding (12837.4 ms p50).
The same configuration encoded a 5-second audio window in 274.6 ms p50 and ran top-k in 0.021 ms p50.
These values describe this host and the pinned CPU model; they do not establish a real-time guarantee.

## Qwen3-0.6B / llama.cpp

Each sample starts a fresh process and reloads the model; the operating system file cache may be warm.

Runtime: `version: 0.7.0-dev (build 11886, commit 2280f0fd1)`

| Threads | Output tokens | Fresh process p50/p95 ms | Prompt tok/s p50/p95 | Generation tok/s p50/p95 | Peak RSS MiB |
|---:|---:|---:|---:|---:|---:|
| 1 | 64 | 2630.7/2838.1 | 154.5/157.6 | 47.1/47.4 | 794 |
| 1 | 128 | 4309.5/4350.4 | 154.2/157.8 | 42.7/43.8 | 795 |
| 1 | 256 | 7833.6/8121.4 | 154.4/154.5 | 39.2/39.3 | 795 |
| 2 | 64 | 2493.5/2578.0 | 273.0/286.4 | 46.3/49.1 | 795 |
| 2 | 128 | 3777.9/3807.8 | 281.7/285.3 | 48.4/48.5 | 794 |
| 2 | 256 | 6855.1/6963.8 | 282.9/285.7 | 44.7/45.6 | 795 |
| 4 | 64 | 2120.0/2189.8 | 541.0/552.4 | 54.5/57.9 | 794 |
| 4 | 128 | 3250.8/3275.9 | 531.1/537.9 | 56.5/56.7 | 794 |
| 4 | 256 | 5607.6/5658.3 | 523.6/526.6 | 55.7/57.1 | 794 |
