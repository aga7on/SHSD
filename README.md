# SHSD

> **Актуальный план (26.10.2026):** [Workspace.md](Workspace.md) · [Todo.md](Todo.md) · [Agents.md](Agents.md) · [протокол оценки](docs/experiments/av-bridge-evaluation-protocol.md) · **[ТЗ для coding-агента F10](docs/experiments/F10-agent-handoff.md)**. Приоритеты: grounded визуальный сюжет и действия, аудиосцена и музыкальная динамика, их временная AV-сшивка, независимые метки и устойчивый 1x CPU live. F10 — Multimodal AV Bridge, не музыкальный классификатор. Обоснованно перспективное обучение **условно разрешено владельцем** (26.10.2026), после technical/data/budget `GO`; [ADR-002](docs/adr/ADR-002-multimodal-bridge-evaluation.md) принята для R&D. [Архив предыдущих документов](docs/archive/2026-10-26-pre-multimodal-review/INDEX.md).

SHSD (Streaming Hierarchical Semantic Decoder) is a local, CPU-first audio/video timeline PoC. The project specification and implementation rules are in [Workspace.md](Workspace.md), [Todo.md](Todo.md), and [Agents.md](Agents.md).

The current implementation includes exact rational PTS conversion, a streaming PyAV reader for audio/video packets, a bounded 600-second media ring, fast/realtime replay control, model-free change detectors, a CPU EmbeddingGemma provider, semantic candidate matching with abstention, a revisioned SQLite timeline, a local bounded Qwen narrator, separate asynchronous L1/L2/L3 job queues, and interval-based progressive watermarks. `shsd analyze` runs a local L0/L1/L2/L3 file pass and writes evidence, revision, caption, and watermark JSONL records.

## Requirements and platform scope

- Python 3.11 or newer.
- PyAV 19.x (installed as a package dependency).
- Initial v0 target platforms: Windows x86_64 and Linux x86_64.
- macOS and ARM64 are outside the initial target and have not been validated.
- The package does not require CUDA. Model runtimes and weights are installed separately and remain local to the machine.

## CPU-only development install

PowerShell on Windows:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Linux:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

The `dev` extra installs Ruff, pytest, mypy, and the explicit artifact-download helper dependency. It does not install CUDA or download model weights. Model IDs, revisions, licenses, file sizes, and checksums are recorded in `models.lock.json`.

For EmbeddingGemma analysis, install the CPU PyTorch pair, then the optional image/audio embedding stack:

```powershell
python -m pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e ".[embedding]"
```

This installs PyTorch/TorchVision CPU wheels; no CUDA runtime is used. The model weights remain a separate explicit download.

EmbeddingGemma and GigaAM extras share the supported Transformers 5.x line, so both can run in one local environment. The pinned GigaAM model predates Transformers 5's meta-device initialization; SHSD loads its module tree on CPU before loading the locked weights.

## Synthetic media fixtures

The small fixture set is generated locally and contains no source recordings. It covers synthetic speech, silence, tones, movement, scene cuts, audio-only, video-only, and 20-second AV sync in MP4 and MKV. The manifest records checksums, stream time bases, expected intervals, labels, and facts the tests must not claim.

To regenerate it, install `ffmpeg`/`ffprobe` and eSpeak NG, then run:

```powershell
python scripts/generate_fixtures.py
```

`python -m pytest` checks the fixture manifest and demuxes all 9 files without network access.

## Local model files

Model downloads are explicit and checksum-verified. For example:

```powershell
python scripts/download_models.py --model qwen3_0_6b
python scripts/download_models.py --runtime llama_cpp
python scripts/smoke_models.py --model qwen3_0_6b --offline
python scripts/download_models.py --model embeddinggemma2
python scripts/smoke_models.py --model embeddinggemma2 --offline
shsd analyze tests/fixtures/media/av_sync_20s.mp4 --levels L0,L1,L2,L3 --cpu-only --offline --output benchmarks/reports/poc_av_sync_20s.jsonl
python -m pip install -e '.[asr]'
python scripts/download_models.py --model gigaam_v3_e2e_ctc
python scripts/smoke_models.py --model gigaam_v3_e2e_ctc --offline
shsd analyze tests/fixtures/media/audio_speech_ru.wav --levels L0,L1 --speech --cpu-only --offline --output runs/speech-demo.jsonl
```

The downloader stores files in the ignored `models/` directory. The smoke script loads from local paths and reports missing or incorrect files instead of fetching them. Model inference results are recorded only after the real CPU smoke runs complete. The optional `--speech` flag runs GigaAM-v3-e2e-CTC locally on bounded 20-second windows; the default stays off. Transcript rows carry source/model metadata and coarse window timestamps, not word timing or diarization. The analyze command embeds fixed-duration audio windows and sampled video frames, reports the top candidates and raw cosine values, and emits `unknown` when configured gates are not met. Similarity values are not probabilities; default thresholds are provisional and can be set with `--minimum-similarity` and `--minimum-margin`.

`shsd analyze` stores normalized vectors in the local model cache. Pass `--cache-dir PATH` to isolate a run or use a separate cache location.

`--vision-profile compact` opts into 140-token image embeddings to reduce CPU inference time; the default `standard` profile uses 280. Profile metadata and cache identities are kept separate. The synthetic A/B evidence and its quality limits are in [`benchmarks/reports/vision_profile_ab_20261026.md`](benchmarks/reports/vision_profile_ab_20261026.md). The stream API accepts the same choice as `vision_profile`.

The L0–L3 file pass emits `watermark` JSONL rows containing `C`, `E`, `D`, `R`, per-level backlog, and visible `skipped`/`unavailable` issues. When `--output` is set, concise cursor progress is also printed to stderr. Requesting L2 or L3 enables the lower semantic prerequisites. Non-exclusive instrument-family candidates are scored independently and every accepted candidate must persist across windows before becoming a separate event; `top_k` only limits the displayed ranking. Captions keep the exact L2 event revisions they describe; if no accepted evidence survives the gates, the output says `narration_skipped` and advances R[L3] with a visible skipped interval. The current file command runs L2 and L3 after its media evidence pass; the independent asynchronous queues are available as a separate worker API.

When both tracks are available, bounded PTS correlation checks scene cuts against audio onsets within 250 ms. Confirmed matches become `cross_modal_coincidence` events with references to both observations and an explicit note that timing does not prove causality. Missing tracks are reported as unavailable; memory-cap overflow is visible as truncated coverage.

The first full PoC has JSONL results for eight local synthetic fixtures in [`benchmarks/reports`](benchmarks/reports), with a human-readable review in [`poc_manual_review.md`](benchmarks/reports/poc_manual_review.md). Those fixtures exercise tones, synthetic speech, silence, motion, scene cuts, and missing modalities; they do not validate real instrument or environmental-noise recognition.

Experimental dynamic hypotheses are opt-in: `shsd analyze clip.wav --levels L1 --iterative-axis instrument_family --cpu-only`. Qwen may propose up to six strings once for that axis; EmbeddingGemma scores them against the media under the same threshold and margin, and duplicate vectors are discarded. The JSONL records both fixed and iterated decisions. With hand-reviewed labels, compare them using `python scripts/evaluate_iterative_hypotheses.py run.jsonl labels.jsonl`. The initial six-window synthetic `speech_presence` A/B showed no quality gain; iterative refinement remains opt-in while representative natural-media labels are still needed.

## Local REST and WebSocket API

Install the optional server dependencies with `python -m pip install -e ".[api]"`, then run `shsd serve`. The server binds to `127.0.0.1:8765` by default, accepts local media files and HTTP(S)/RTSP(S) URLs, and stores revision history under `runs/shsd/`. Use `DELETE /v1/streams/{id}` to request a cooperative stop. RTSP jobs default to `drop_oldest`; the request may select `drop_newest`. REST endpoints expose stream status, current/history timeline rows, event revisions, watermarks, metrics, and post-analysis L2/L3 refinement. Refine work uses a bounded 32-entry priority queue (L2 before L3), coalesces touching queued L3 ranges for the same stream, and responds with HTTP 429 when saturated. Connect to `/v1/streams/{id}/ws?after_seq=N` to replay retained messages after a client sequence number; if the bounded message window expired, the server sends `stream.gap_detected` and points to REST backfill.

The API currently runs local files only. Live URL ingestion, pause/resume/seek control, and replay across a server restart are still open.

Open `http://127.0.0.1:8765/ui/` after starting `shsd serve` to use the local rolling timeline. The dashboard shows Video, Music, Sound, Speech, and L1–L3 lanes, the C/E/D/R cursors, selected-level backlog, event evidence and revision history, and a manual L2/L3 refine form. The source form has an opt-in GigaAM ASR switch; transcript windows appear on the Speech lane and remain separate from music and visual events. The timeline follows the latest processed media time and shows at most ten minutes.

Completed streams can be exported without rerunning inference: use the dashboard's JSON, JSONL, or Markdown buttons, or request `/v1/streams/{id}/export?format=json|jsonl|markdown`. JSON includes current events and can include revisions with `include_history=true`; all formats include saved captions, current ASR segments, and warnings for missing coverage, failed ASR windows, or uncertain claims. The `/v1/streams/{id}/speech` endpoint returns persisted transcript segments. Captions and stream metadata are stored in SQLite and survive API restarts. Queued/running jobs are reported as interrupted after restart and are not resumed.

To verify local Qwen narration from a fixed accepted-claim input, run
`python scripts/smoke_narrator.py --threads 4`. The report is written to
`benchmarks/reports/narrator_smoke.json`; each generation is bounded by token, timeout, and input-size limits.

EmbeddingGemma smoke encodes local text, image, audio, and video inputs. GigaAM is an optional Russian ASR profile; its PyTorch and torchaudio CPU builds are installed separately, and ASR remains disabled in the default runtime profile.

## Local media replay

The installed CLI can read local media as fast as possible or pace packets against source time:

```powershell
shsd replay tests/fixtures/media/av_sync_20s.mkv --fast
shsd replay tests/fixtures/media/video_static_3s.mp4 --simulate-realtime
```

Realtime replay also accepts `--speed` to scale the wall-clock pacing. Replay sends compressed packets through a bounded 10-minute ring (64 MiB memory plus up to 256 MiB spill), and its JSON summary reports ring occupancy/drops, per-modality capture watermarks, source-time bounds, and optional host CPU/RSS and pressure state. `benchmarks/reports/replay_ingest_smoke.json` records a 20-second A/V replay run. `shsd analyze` uses the same ring limits and reads compressed packets through leases before PyAV decode; L2 event refinements use the bounded semantic scheduler. Its A/V report is `benchmarks/reports/analyzer_av_ring_smoke.jsonl`.

`shsd analyze` samples host CPU/RSS and ring occupancy, preserves L1 under critical pressure, and records rejected L2 work as `runtime_backpressure` coverage. Audio decode/windowing runs in a bounded producer queue while the consumer applies results. A shared bounded serial embedding worker accepts audio and frame jobs in timestamp order; L1 matching, temporal reduction, and SQLite writes remain on the consumer thread. `analyzer_av_ring_smoke.jsonl` records 1,139 packets, C/E=20,000 ms, zero drops, a video queue peak of 8/8, one 342 ms producer stall, and a full-call 50 ms process-tree RSS high-water mark of 2.43 GB across one process; L1 completed while 14 L2 jobs were rejected under measured queue pressure. The bounded embedding-worker smoke is recorded in `benchmarks/reports/analyzer_embedding_worker_smoke.md`; it verifies 9/9 completed jobs and final C/E/D/R=20,000 ms, but is not a speed comparison. Load-aware L1 admission, live ingest, and sustained 2×/5× full-stack RAM/latency remain open.

For bounded queue pressure experiments, `shsd analyze` accepts `--prefetch-overflow-policy block|drop_newest|drop_oldest` and `--prefetch-capacity N`. The default is blocking with modality capacities of 64 audio items and 8 video items. Opt-in drop modes record dropped embedding coverage; `benchmarks/reports/analyzer_prefetch_drop_smoke.md` documents a capacity-1 A/V run. Local file analysis remains the default producer/consumer path. `shsd analyze` accepts PyAV-readable HTTP(S)/RTSP(S) URLs, uses one shared audio/video demux after metadata inspection, and removes credentials/query tokens from JSONL, API, and persisted source labels. A local HTTP A/V fixture reached C/E=20,011 ms with zero drops; RTSP defaults to `drop_oldest` and rejects blocking mode. The API accepts URL jobs and supports `DELETE /v1/streams/{id}` with bounded remote-read timeouts. A local MediaMTX+FFmpeg RTSP smoke processed 1,822 packets through one decoder demux and stopped an active API stream in 722 ms; it recorded 77 bounded prefetch drops and zero ingest drops. Physical-camera behavior, reconnect, and cancellation during a stalled network read remain open.

For parallel full-stack A/V scale checks, run `python scripts/benchmark_fullstack.py --streams 2 5 --cycles 1`. Use `--duration-minutes 1`, `5`, `10`, or `30` for repeated replay soaks. Pass `--isolated-cache` for a separate embedding cache per stream and cycle when measuring cold media inference; the default shared cache measures the warmed repeated-file path. The 30-minute baseline report is `benchmarks/reports/fullstack_av_30m_soak.md` (JSON alongside it). It completed 105 cycles at 2x and 92 at 5x with zero coverage misses, ingest/prefetch drops, or scheduler rejects. Per-stream RTF p50/p95/max was 0.859/0.873/0.885 at 2x and 0.981/0.991/1.002 at 5x; peak aggregate process-tree RSS was 4.69/11.71 GiB and disk queue p95 was zero. RTF includes full CLI wall time. A sampled first-cycle timeline had 9/9 embedding cache hits, so these are warm-cache repeated-file results, not unique-media throughput. The lag percentiles use finite-file timeline watermarks; final lag returned to zero, so these runs do not measure progressive live-camera latency. The post-worker cold-cache smoke reached 1.76–1.77 RTF at 2x and 2.01–2.03 at 5x; at 5x the load controller rejected lower-priority L2 jobs while retaining completed L1 coverage. See [`benchmarks/reports/fullstack_embedding_worker_cold_cache.md`](benchmarks/reports/fullstack_embedding_worker_cold_cache.md) and [`docs/adr/ADR-001-next-version-performance.md`](docs/adr/ADR-001-next-version-performance.md) for the model and runtime decision.

## Repository layout

- `src/shsd/` — installable Python package and CLI.
- `configs/` — runtime, hypothesis, and prompt configuration as those features are implemented.
- `tests/` — unit, integration, regression, and fixture areas.
- `scripts/` — local development and maintenance scripts.
- `benchmarks/` — benchmark fixtures and measured reports.
- `docs/adr/` — accepted or proposed architectural decisions.
- `Workspace.md` — target module layout and API/data contracts.

The planned runtime separates media ingestion/clocking, cheap signal detectors, CPU embedding workers, semantic matching, optional ASR, narration, and a single timeline writer. Async code handles scheduling and I/O; heavy CPU inference belongs in a bounded process pool. Bounded queues and explicit gaps/backpressure are part of the design. The planned module tree is recorded in `Workspace.md`; empty implementation modules are added with their corresponding tasks.

## Development checks

```bash
python -m pytest
ruff check .
mypy
```

The unit tests cover package import/version, help output, PTS/epoch behavior, all media fixtures, offline artifact errors, and ring capacity/leases. `tests/unit/test_package_imports.py` imports every shipped module so a source package that is missing from the repository fails immediately instead of surfacing as unrelated collection errors. Tests that need the optional PyTorch stack are skipped in a `dev`-only install.

`mypy` is configured as `strict` and is not yet green; the remaining errors and the full repository audit are in [`docs/audit/2026-10-28-repository-audit.md`](docs/audit/2026-10-28-repository-audit.md). `.github/workflows/ci.yml` runs Ruff and pytest as blocking steps and `mypy` as advisory until that backlog is closed.

## Latest full-stack measurements (2026-10-26)

Detailed feature comparisons are in [`benchmarks/reports/fullstack_feature_ab.md`](benchmarks/reports/fullstack_feature_ab.md), with machine-readable values in the adjacent JSON. Qwen L3 measured 30.9 tokens/s at 2x and 12.3 at 5x, while its per-stream RTF exceeded 1 at both scales. The source-only template fallback stayed below RTF 1 and took under 0.05 ms p95 to construct. GigaAM ASR and dynamic hypothesis generation remain opt-in based on their measured runtime, memory, and proposal timeouts. The earlier 10-minute run is historical because its end-of-file scheduler rejects preceded the `current_depth` fix; `fullstack_pressure_recheck.md` records the corrected zero-reject result. The 30-minute baseline and next-version decision are recorded in `benchmarks/reports/fullstack_av_30m_soak.md` and `docs/adr/ADR-001-next-version-performance.md`. Adaptive sampling is available as `shsd analyze --sampling-profile adaptive`; its exploratory natural-window and synthetic silence A/B results are in `benchmarks/reports/adaptive_sampling_natural.md` and `benchmarks/reports/adaptive_sampling_silence_ab/sampling_profiles_ab.md`. Keep it opt-in because the natural set showed no embedding reduction. `F6.01` and `F6.02` remain active.


## Quality and realtime status (2026-10-26)

The 90-second offline `Tears of Steel` run yielded 1 policy-accepted, not independently verified percussion detail and 3 mostly generic Russian L3 captions ([review](benchmarks/reports/music_multiclass_l2_20261026/real_video_quality_review.md)). The 60-second 1x live Qwen v2 test reached only 41.828 seconds of capture, with 503 shared-prefetch drops and L1 median lag 22.27 seconds ([report](benchmarks/reports/live_qwen_v2_60s_20261026/report.md)). These are **not** proof of music accuracy or realtime. The new F7–F10 roadmap, including a **parallel trainable multimodal bridge R&D track** (training conditionally authorized after feasibility/data/budget GO), and evaluation protocol are in [Todo.md](Todo.md) and [the bridge pilot](docs/experiments/bridge-training-pilot.md).


## Исполняемое обучение F10: изображения, видео, аудио и AV

Актуальный [training design](docs/experiments/F10-multimodal-training-design.md) включает отдельные IMAGE-only, VIDEO-only, AUDIO-only и AV режимы, тензорные контракты, JSONL разметку, target-only CE, masks, начальные гиперпараметры и критерии независимого качества/CPU realtime. [Поручение coding-агенту](docs/experiments/F10-agent-handoff.md). Изменения документации не означают, что модель уже обучена или проверена.
