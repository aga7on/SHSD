# F9.01: capture queue pressure on CPU live Qwen

Status: **partial**, 1x not met. Base commit `ccd8b3d`, with the capture-coalescing and prefetch shutdown changes in the accompanying commit. Tests and runs below are from the working tree containing those changes; no model weights were changed.

The live producer now combines contiguous or overlapping capture intervals with the same modality, status and reason, and emits an aggregate when its source-time duration reaches 250 ms. Real gaps and dropped spans stay separate. On cancellation, pending capture coverage is reported and the prefetch source is closed. This reduces the number of capture records competing for the bounded media queue. It does not increase semantic detection quality by itself.

## Live measurements

Windows 11 Pro for Workstations, AMD Ryzen 9 9900X3D, 4 configured CPU threads, 5 s windows, standard audio/video sampling, cold embedding cache, local MediaMTX 1.21.2 RTSP, unlooped `tears_of_steel_120_210s.mp4`, 60 s publisher, Qwen3-0.6B Q8_0 L3 enabled, ASR disabled. EmbeddingGemma revision `914f7f89142e33e77833254d9c9b90c3cef7303b`; Qwen revision `13ac06624948e4d8589cb4b6f90100837342fcb8`. Values below are observed before stop, except queue counts and process-tree RSS from the final runtime summary.

| Run | Capture / 60 s | Embedding coverage | L1 / L2 / L3 R cursors at last pre-stop sample | Captions before stop | Caption lag median | Shared queue produced / dropped |
|---|---:|---:|---|---:|---:|---:|
| Previous baseline | 41.818 s | 35.099 s | 35.099 / 25.099 / 25.099 s | 2 | 20.758 s | 2863 / 548 |
| Direct producer watermark update, rejected | 16.250 s | 10.001 s | 15.099 / 5.099 / 5.099 s | 0 | unavailable | 14 / 0 |
| Coalesced capture, first run | 42.014 s | 35.096 s | 35.096 / 30.096 / 33.139 s | 2 | 17.893 s | 406 / 71 |
| Coalesced capture, shutdown fix | 42.006 s | 35.110 s | 35.110 / 25.110 / 30.037 s | 3 | 17.704 s | 403 / 48 |

The final run had 0 ring ingest drops, 3.435 GB peak process-tree RSS, and L2 reported zero confirmed refinements. Its 3 pre-stop captions and 17.704 s median lag are a small sample; they do not prove a stable latency reduction. Shared-queue item counts are **not directly comparable** after aggregation: one item can now represent multiple capture packets. Neither the queue counter nor the unchanged capture/embedding coverage demonstrates that loss of useful media work was eliminated. This run does not meet sustained 1x and does not establish visual-action or music-transition accuracy. Two Qwen fallback outputs occurred across all five captions including post-stop output; no L2 music transition was confirmed.

Raw records: [previous baseline](live_qwen_current_20261027/report.json), [rejected direct update](live_capture_direct_20261027/report.json), [coalesced first run](live_capture_coalesced_20261027/report.json), [coalesced final run](live_capture_coalesced_final_20261027/report.json).

## Reproduction and checks

```powershell
.venv/Scripts/python.exe scripts/benchmark_live_qwen.py --mediamtx C:/Users/ARTEM/AppData/Local/Temp/shsd-mediamtx-1.21.2/mediamtx.exe --source benchmarks/fixtures/real_poc/tears_of_steel_120_210s.mp4 --output-dir benchmarks/reports/bridge_f10/live_capture_coalesced_final_20261027 --cache-dir benchmarks/reports/bridge_f10/live_capture_coalesced_final_20261027/cache --threads 4 --window-ms 5000 --live-seconds 60 --poll-seconds 0.5 --post-stream-timeout-seconds 120
.venv/Scripts/python.exe -m pytest tests/unit/test_analyze.py tests/unit/test_prefetch.py tests/unit/test_temporal_semantic.py tests/unit/test_semantic.py -q
.venv/Scripts/python.exe -m pytest tests/unit -q
.venv/Scripts/python.exe -m ruff check src/shsd/analyze.py src/shsd/ingest/prefetch.py tests/unit/test_analyze.py tests/unit/test_prefetch.py
.venv/Scripts/python.exe -m ruff format --check src/shsd/analyze.py src/shsd/ingest/prefetch.py tests/unit/test_analyze.py tests/unit/test_prefetch.py
.venv/Scripts/python.exe -m mypy
```

Live benchmark exit 0; targeted tests 45 passed; full unit suite 279 passed; Ruff check and format passed. Project-wide mypy exited 1 with 38 errors in 8 files, including type narrowing errors in `bridge/dataset.py`, existing `graph.py`/`narrator.py` typing errors and missing stubs for `psutil` and `threadpoolctl`. No clean mypy result is claimed.

Next: measure actual lost audio windows and selected frames separately from coalesced capture records; profile capture and embedding bottlenecks; retain independent human review for VIDEO actions and AUDIO music transitions. B1 remains NO-GO.
