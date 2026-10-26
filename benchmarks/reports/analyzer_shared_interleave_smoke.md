# Shared media admission smoke

## Change

`analyze_media()` now sends audio windows and selected video frames through one bounded admission heap. `iter_merge_by_key()` keeps one lookahead item per source, rejects a source that moves backward in work-ready time, and exposes capacity/peak/admitted/dispatched counts. At equal ready times, capture/drop coverage spans are admitted before model work; remaining ties preserve source order. One consumer performs embedding and L1 work for both modalities.

The merge key is monotonic work-ready time: capture spans use their end time, audio windows use their end time, and video frames use PTS clamped to the latest ready capture time. This interleaves work as each modality becomes available. It does not order outputs by interval start; a video frame at 5.1 s may be admitted before an audio window covering 0-5 s if that audio window is not ready yet.

The bounded prefetch primitive now offers `block`, `drop_newest`, and `drop_oldest` overflow policies. Both drop modes increment `dropped_count` and call the drop callback with `prefetch_queue_full`; the analyzer preserves capture status and writes dropped audio/video embedding coverage. File analysis defaults to `block`; opt-in queue policies and capacity are exposed for controlled pressure runs. No network/camera source is wired yet.

## Verification runs

All runs used the local pinned CPU model, offline mode, four threads, and the CLI. The A/V fixture requested L0/L1/L2; the audio-only and video-only checks requested L0/L1.

| Input | Duration | Embedding emissions (modality@interval-start) | C/E final | Drops | L2 state events | End-to-end |
|---|---:|---|---:|---:|---:|---:|
| A/V 20-second fixture | 20000 ms | image@100, audio@0, image@5100, audio@5000, image@10100, audio@10000, image@15100, audio@15000, audio@20000 | 20000/20000 ms | 0 | 14 | 13.131 s |
| 20-second environmental audio corpus | 20000 ms | audio@0, audio@5000, audio@10000, audio@15000 | 20000/20000 ms | 0 | 0 | 12.447 s |
| 3-second static video fixture | 3000 ms | image@100 | 3000/3000 ms | 0 | 0 | 11.843 s |

A/V run details: scheduler backpressure count `0`, peak process-tree RSS `2432905216` bytes, A/V ring captured 1,139 packets (939 audio, 200 video), and all L1/L2/L3 read cursors reached 20,000 ms. The output includes four image and five audio embeddings; no drops were recorded. The shared scheduler held at most 2/2 lookahead items and admitted/dispatched 1,164 items. The audio prefetch queue peaked at 64/64 and video at 8/8; producers reported 0 blocking episodes. The 13.131-second elapsed time includes cold model/profile initialization (`embedding_model_and_text_profiles` was 12467.4 ms); it is not a warm-throughput result.

The audio-only run reached C/E/R=20,000 ms without drops. The video-only run reached C/E/R=3,000 ms and emitted its image embedding. These checks cover all modality-presence branches after the refactor.

`audio_consumer_work` and `video_consumer_work` measure time processing items in the merged loop. `shared_media_interleave` is the wall time for the complete merge, including waits for prefetched items.

## Remaining F6.01 work

The shared scheduler currently uses priority only to put coverage updates ahead of model work on equal ready times; embedding/matching still execute serially on the CPU consumer. Live ingest is not connected to the new explicit prefetch drop policies, and sustained 2x/5x full-stack RAM/latency soak runs remain unimplemented. This smoke does not close the F6.01 DoD.

Commands used:

```powershell
.\.venv\Scripts\shsd.exe analyze tests\fixtures\media\av_sync_20s.mp4 --levels L0,L1,L2 --cpu-only --offline --threads 4 --window-seconds 5 --stream-id analyzer-shared-admission-smoke-current --output benchmarks\reports\analyzer_shared_interleave_smoke.jsonl
.\.venv\Scripts\shsd.exe analyze benchmarks\evaluation\iterative_speech_presence_natural\inputs\environmental_sounds.wav --levels L0,L1 --cpu-only --offline --threads 4 --window-seconds 5 --stream-id audio-only-shared-interleave-smoke --output benchmarks\reports\audio_only_shared_interleave_smoke.jsonl
.\.venv\Scripts\shsd.exe analyze tests\fixtures\media\video_static_3s.mp4 --levels L0,L1 --cpu-only --offline --threads 4 --window-seconds 5 --stream-id video-only-shared-interleave-smoke --output benchmarks\reports\video_only_shared_interleave_smoke.jsonl
```

Validation: 145 unit tests passed; Ruff passed across `src`, `tests`, and `scripts`; mypy passed for 44 source files. The A/V, audio-only, and video-only offline CLI runs completed successfully. The refreshed A/V run uses the default blocking prefetch policy and reports `dropped_count=0` for both modality queues.
