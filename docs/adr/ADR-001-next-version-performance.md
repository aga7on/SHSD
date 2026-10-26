# ADR-001: Preserve the pinned encoder and improve runtime scheduling

- Status: Accepted
- Date: 2026-10-26
- Context: F6.03 full-stack CPU benchmark and existing feature A/B evidence

## Context

The 30-minute repeated A/V replay used the pinned EmbeddingGemma2 revision on CPU with L0/L1/L2 enabled. At 2 concurrent streams, 105 cycles processed 4,200 media-seconds with per-stream RTF p50/p95/max of 0.859/0.873/0.885. At 5 streams, 92 cycles processed 9,200 media-seconds with RTF 0.981/0.991/1.002. Both scales recorded zero dropped or failed coverage, ingest drops, prefetch drops, or scheduler pressure rejects. Peak process-tree RSS was 4,694 MiB at 2x and 11,712 MiB at 5x. Disk queue p95 was zero, with maxima of 5 and 6. This was a warm-cache repeated-file run: a sampled first-cycle timeline had nine embedding records and all nine were `cache_hit=true`. It is useful evidence for sustained process, queue, and memory behavior with repeated identical media, but it does not measure unique-media encoder throughput.

The lag report's p95 reached 20 seconds at both scales because the analyzer reports finite-file watermark progress while the 20-second fixture is being consumed, then drains L2 refinement at end of pass. Final watermarks returned to zero lag. This run is sustained local-file replay, not a live-camera latency measurement.

A new isolated-cache one-cycle comparison measured uncached media work. It uses a separate embedding cache for each stream: per-stream RTF was 1.76–1.77 at 2x and 2.01–2.03 at 5x. Each process spent 13.6–15.8 s initializing model/profile vectors and 19.3–22.0 s encoding the 20 s source. At 5x, the load controller rejected 14 L2 jobs per stream while retaining L1 and completing media coverage; aggregate peak process-tree RSS was 11,792 MiB. A separate single-stream cold smoke took 32.48 s including model/profile initialization for a 20 s source. These are one-cycle fixtures, not endurance or natural-media evaluations, but they show that unique-media processing is not realtime at the measured settings. The earlier warm-cache RTF must not be used to claim otherwise.

A 5x follow-up with two CPU threads per process took 55.6 s for the same 20 s fixture (per-stream RTF 2.76–2.78), slower than the four-thread run. It recorded no L2 pressure rejects, but that does not offset the lower media throughput. Retain four threads as the measured setting for this workload; a broader thread-count matrix is still needed.

The feature A/B report shows that Qwen narration raises RTF above 1 at both tested scales, while template narration is below 1. GigaAM ASR substantially increases RAM. Iterative text-hypothesis proposals did not improve ranking on the exploratory natural set and timed out at 5x. These optional stages were absent from the 30-minute baseline.

## Decision

- Keep the pinned EmbeddingGemma2 encoder and CPU inference as the current default because no controlled quality comparison justifies replacing it. Do not claim realtime unique-media processing: cold-cache runs were above RTF 1 at 2x and 5x, while the 30-minute result measured warm-cache repeats.
- Do not train a projector by default. There is no representative evidence of embedding information loss that would justify adding a trainable alignment stage.
- Do not change NCM without a separate, controlled comparison and a new ADR.
- Preserve an explicit CPU real-time profile: ASR, Qwen L3 narration, and iterative proposals remain opt-in. If live latency pressure appears, use template narration or defer L3; measure any change against the same source and report recall.
- Prioritize a persistent model process, then measure and reduce uncached audio/frame inference time and finish shared bounded L1 admission/scheduling. Cached profile vectors can amortize initialization, but the cold check shows media inference itself also consumes roughly one source-duration at 2x and more at 5x.
- Keep standard sampling as the default until adaptive sampling has a broader hand-labeled recall evaluation. Adaptive sampling may be offered as an explicit profile with a heartbeat and visible skipped-coverage records.

## Rejected for this version

- Replacing the audio/video encoder immediately: deferred because the cold result establishes a throughput gap but no controlled quality/latency comparison supports choosing a replacement yet.
- Training a projector: rejected because the evaluation set is too small to characterize information loss and no evidence supports this added training path.
- Reopening NCM: rejected until a separate benchmark compares its quality and runtime against the current matcher.
- Enabling Qwen, ASR, or iterative proposals by default for 5x CPU operation: rejected by their measured latency/RAM costs and lack of quality improvement on current evidence.

## Follow-up

F6.01 remains open for real RTSP behavior and a load-aware shared scheduler that admits embedding/L1 work as bounded jobs. The serial background embedding worker is a step toward that goal, not a completed semantic scheduler. F6.02 remains open for representative adaptive-sampling recall/RTF evidence. Repeat the full-stack soak with `--isolated-cache` before making unique-media throughput claims; the 28-window natural speech-presence set remains exploratory and must not be presented as representative.
