# F10-GO — current training gate

**Decision: NO-GO for B1 training as of 2026-10-27.** This records the available evidence and current blockers; it is not a request for renewed owner authorization. No bridge training has started, and no trained weights exist.

## Hypothesis and scope

B1 is the first trainable **Multimodal AV Bridge**: frozen EmbeddingGemma 2 plus frozen Qwen3-0.6B, with a small trainable visual/audio projector and temporal resampler. IMAGE, VIDEO, AUDIO, and synchronized AV are co-primary modes. Targets are structured grounded events/claims plus chronological Russian narration. A music-only score cannot pass this gate.

The current B0 graph improves claim provenance and accepted-claim narration, but it does not yet represent tracked visual entities/actions or music-layer transitions as typed nodes. The feature batch and dataset schema are in place as interfaces, but neither is connected to the production `analyze` path or backed by an independently labeled corpus.

## Technical gate

| Check | Status | Evidence and limit |
|---|---|---|
| EmbeddingGemma IMAGE/VIDEO/AUDIO/AV pooled and token outputs | **PASS: API shape only** | [`production_sequence_smoke.json`](production_sequence_smoke.json), pinned revision `914f7f89142e33e77833254d9c9b90c3cef7303b`; token widths 768, sampled frame PTS preserved. One 5s VIDEO call took 4.18s on CPU; this is not a stream result. |
| Qwen external conditioning | **PASS: transport only** | [`llama_cpp_prefix_smoke.json`](llama_cpp_prefix_smoke.json) verifies a synthetic `[4,1024]` external prefix through the pinned CPU llama.cpp C API. The values are untrained and prove no useful conditioning. |
| Frozen Qwen gradient path for projector training | **PASS: API smoke only** | [`capability_matrix.md`](capability_matrix.md) records a synthetic Transformers `inputs_embeds` forward/gradient/generate probe. This is not learned bridge quality. |
| Production sequence-to-bridge data path | **PARTIAL** | `AVFeatureBatch` preserves one IMAGE sequence per exact frame PTS and a separate AUDIO interval sequence; 23 unit tests cover its masks, ordering, dimensions, provenance and modality requirements. No integration smoke or end-to-end Qwen call has been run for this adapter. Default `analyze` still uses pooled records. |
| Cross-manifest source leakage | **PASS: validator behavior only** | `validate_manifests()` and CLI `--train/--val/--test` reject split mismatch, duplicate sample IDs, and cross-split source group/ID/SHA collisions. No real corpus exists to validate. |
| CPU prefill/decode/RSS under sustained stream load | **NOT MET** | The existing 85-second live Qwen run emitted zero captions before stop; L2/L3 cursors were 93ms and the first caption arrived 4.154s after stop. The live path does not yet provide online L2/L3 latency. No sustained B1 1x test exists. |
| Model/runtime licenses | **PARTIAL** | Pinned model and llama.cpp licenses are recorded in `capability_matrix.md`. No training data source has been selected, rights-reviewed, or approved for the required uses. |

## Data, baseline, and evaluation

- **Licensed source-separated train/val/held-out:** none selected; **0 source groups verified** for F10 training.
- **Independent F10 labels:** **0** delivered/verified across IMAGE, VIDEO, AUDIO, and AV. The existing 40-clip speech review pack is source-description-derived and is not independent ground truth. Do not use it for B1 or prompt tuning.
- **Schema and leakage checks:** [`av_bridge_sample_v1.schema.json`](../../../configs/schemas/av_bridge_sample_v1.schema.json) and [`validate_bridge_dataset.py`](../../../scripts/validate_bridge_dataset.py) are implemented. There is no eligible manifest to validate yet.
- **A0/B0 baseline:** a 90s `Tears of Steel` offline B0 graph run is recorded in [`real_video_quality_review_b0_graph.md`](../music_quality_v2/real_video_quality_review_b0_graph.md). It produced 62 L1 and 62 L2 revisions, 3 L3 descriptions, 2 safe fallbacks, and zero new accepted L2 details. The 20s VIDEO-only pass had 24/24 uncertain visual matches and no action node; the AUDIO-only pass had no confirmed music/transition. The new [initial B0/CPU audit](f10_02_initial_b0_cpu_audit.md) includes commands and raw output. These runs have no independent human labels and are not visual/music quality accuracy scores.
- **Semantic diagnosis:** [`semantic_matcher_diagnostic.md`](../semantic_matcher_diagnostic_20261026/semantic_matcher_diagnostic.md) reports 95 uncertain / 5 accepted over 100 window matches; this is label-free and cannot be treated as accuracy.
- **Registered success thresholds:** not set on independent validation data. IMAGE entity/relation, VIDEO action/identity/order, AUDIO layer/transition, AV sync, factual Russian narration, and cross-mode non-regression must each have a defined threshold before held-out evaluation.

## Resources and stop rules

- Owner authorization for prospective training is already recorded; it applies only after the gates below pass.
- The design limits the initial pilot to at most 1,000 optimizer steps or 3 epochs, whichever comes first, but **no explicit maximum GPU-hours, verified training device/VRAM, or disk budget is recorded**.
- Early-stop reasons are documented in the design, but exact validation cadence, per-mode numeric thresholds, and measured CPU 1x limits are not frozen against independent data.

## Required evidence to change NO-GO

1. Secure rights-cleared, source-separated training and validation groups plus a held-out evaluation set; record provenance and permitted use in the manifest.
2. Obtain blind human labels for all four modes, including visual entity continuity/actions/order and AV alignment; freeze per-mode metrics and non-regression criteria before evaluating held-out.
3. Connect the PTS-preserving feature adapter to the B0 graph/evidence path; obtain independent confirmation for the provisional source-time visual action, add supported entity/action/object and audio-transition events, then freeze same-source A0/B0 outputs. Current local evidence shows these conditions are not yet met.
4. Record a bounded GPU-hours/VRAM/disk budget and validation/stop schedule in this file before training.
5. Run shape, masking, target-only loss, frozen-weight, and small train-only overfit checks, then make a measured CPU prefix/live plan. Training may start only after these entries are evidence-backed and the decision is explicitly changed to GO.

No production deployment decision is made here. A B1 model must still improve grounded factuality without unacceptable regression in visual or audio quality and meet sustained CPU 1x before production use.
