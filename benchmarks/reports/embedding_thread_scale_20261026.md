# SHSD CPU baseline

Generated: `2026-10-26T08:20:58.151040+00:00`

## Machine

- CPU: AMD Ryzen 9 9900X3D 12-Core Processor
- OS / Python: Windows-11-10.0.26200-SP0 / 3.14.6
- Cores: 12 physical, 24 logical
- ISA flags: avx, avx2, avx512bitalg, avx512bw, avx512cd, avx512dq, avx512f, avx512ifma, avx512vbmi, avx512vbmi2, avx512vl, avx512vnni, avx512vpopcntdq, sse, sse2, sse4_1, sse4_2, sse4a
- RAM: 95909 MiB
- Embedding model load: 15279.9 ms
- Embedding model load process-tree peak RSS: 2320 MiB

## EmbeddingGemma 2

Latency is CPU wall time per encode call. Repeated inputs use distinct cache keys; recorded cache hits are flagged.

| Threads | Audio | Mean ms | p50 ms | p95 ms |
|---:|---:|---:|---:|---:|
| 4 | 3s | 198.1 | 198.1 | 211.8 |
| 4 | 5s | 256.7 | 256.7 | 263.8 |
| 4 | 10s | 470.9 | 470.9 | 473.1 |
| 6 | 3s | 184.6 | 184.6 | 196.5 |
| 6 | 5s | 244.0 | 244.0 | 245.9 |
| 6 | 10s | 373.7 | 373.7 | 387.6 |
| 8 | 3s | 153.1 | 153.1 | 159.1 |
| 8 | 5s | 190.2 | 190.2 | 197.7 |
| 8 | 10s | 288.1 | 288.1 | 291.3 |
| 12 | 3s | 166.7 | 166.7 | 177.5 |
| 12 | 5s | 200.0 | 200.0 | 203.4 |
| 12 | 10s | 304.1 | 304.1 | 306.8 |

### Other stages

| Threads | Text p50/p95 ms | Frame p50/p95 ms | Video p50/p95 ms | Joint AV p50/p95 ms | Top-k p50/p95 ms |
|---:|---:|---:|---:|---:|---:|
| 4 | 41.5/43.6 | 4037.5/4053.0 | 12635.7/12641.0 | 9910.2/9941.7 | 0.065/0.098 |
| 6 | 36.0/37.0 | 2869.2/2885.8 | 9720.8/10027.2 | 7534.7/7543.2 | 0.039/0.062 |
| 8 | 35.0/37.0 | 2217.3/2228.4 | 8070.7/8143.5 | 6299.2/6408.2 | 0.061/0.101 |
| 12 | 39.1/42.2 | 1569.8/1588.7 | 6103.0/6160.5 | 4972.5/5187.9 | 0.046/0.067 |

## Process scaling

Three-second audio windows run with one CPU thread in each worker.

| Processes | Tasks | Wall ms | Tasks/s | Task p50 ms | Peak process-tree RSS MiB |
|---:|---:|---:|---:|---:|---:|
| 1 | 2 | 13226.0 | 0.151 | 404.2 | 4622 |

## Measured workload notes

At 4 threads, the slowest measured stage was 8-second video embedding (12635.7 ms p50).
The same configuration encoded a 5-second audio window in 256.7 ms p50 and ran top-k in 0.065 ms p50.
These values describe this host and the pinned CPU model; they do not establish a real-time guarantee.

## Qwen3-0.6B / llama.cpp

Each sample starts a fresh process and reloads the model; the operating system file cache may be warm.

Runtime: `version: 0.7.0-dev (build 11886, commit 2280f0fd1)`

| Threads | Output tokens | Fresh process p50/p95 ms | Prompt tok/s p50/p95 | Generation tok/s p50/p95 | Peak RSS MiB |
|---:|---:|---:|---:|---:|---:|
| 4 | 64 | 1792.5/1800.1 | 561.4/595.8 | 63.0/63.1 | 794 |
| 4 | 128 | 2786.9/2795.9 | 594.6/596.6 | 63.0/63.1 | 794 |
| 4 | 256 | 4953.1/4953.5 | 589.8/591.5 | 61.2/61.3 | 795 |
| 6 | 64 | 1839.3/1924.3 | 774.5/782.6 | 65.7/66.0 | 795 |
| 6 | 128 | 2694.1/2705.1 | 852.5/860.9 | 65.8/65.8 | 794 |
| 6 | 256 | 4745.0/4792.2 | 832.5/837.2 | 64.1/64.8 | 795 |
| 8 | 64 | 1705.4/1707.6 | 853.0/905.3 | 68.3/68.8 | 794 |
| 8 | 128 | 2813.1/2827.5 | 782.1/782.7 | 64.7/67.9 | 795 |
| 8 | 256 | 4547.8/4551.8 | 968.6/982.5 | 67.3/67.4 | 795 |
| 12 | 64 | 1717.2/1726.3 | 848.3/857.9 | 66.5/67.5 | 795 |
| 12 | 128 | 2682.0/2709.7 | 853.9/861.5 | 66.5/66.9 | 795 |
| 12 | 256 | 4751.9/4810.0 | 849.8/858.7 | 64.3/65.3 | 795 |
