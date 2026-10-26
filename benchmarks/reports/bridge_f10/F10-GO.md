# F10-GO — current training gate

**Decision: NO-GO for B1 training as of 2026-10-27.** This records the available evidence and current blockers; it is not a request for renewed owner authorization. No bridge training has started, and no trained weights exist.

## Hypothesis and scope

B1 is the first trainable **Multimodal AV Bridge**: frozen EmbeddingGemma 2 plus frozen Qwen3-0.6B, with a small trainable visual/audio projector and temporal resampler. IMAGE, VIDEO, AUDIO, and synchronized AV are co-primary modes. Targets are structured grounded events/claims plus chronological Russian narration. A music-only score cannot pass this gate.

The current B0 graph improves claim provenance and accepted-claim narration, but the default `analyze` route does not yet extract tracked visual entities/actions or music-layer transitions as typed nodes. An optional feature-batch input carries per-frame PTS and provenance into EventGraph. A separate pinned zero-shot X-CLIP diagnostic can attach a source-time entity/action/object hypothesis, but it is unverified, is not sent to Qwen, is not integrated into the default route, and is not backed by independent labels.

## Technical gate

| Check | Status | Evidence and limit |
|---|---|---|
| EmbeddingGemma IMAGE/VIDEO/AUDIO/AV pooled and token outputs | **PASS: API shape only** | [`production_sequence_smoke.json`](production_sequence_smoke.json), pinned revision `914f7f89142e33e77833254d9c9b90c3cef7303b`; token widths 768, sampled frame PTS preserved. One 5s VIDEO call took 4.18s on CPU; this is not a stream result. |
| Qwen external conditioning | **PASS: transport only** | [`llama_cpp_prefix_smoke.json`](llama_cpp_prefix_smoke.json) verifies a synthetic `[4,1024]` external prefix through the pinned CPU llama.cpp C API. The values are untrained and prove no useful conditioning. |
| Frozen Qwen gradient path for projector training | **PASS: API smoke only** | [`capability_matrix.md`](capability_matrix.md) records a synthetic Transformers `inputs_embeds` forward/gradient/generate probe. This is not learned bridge quality. |
| Production sequence-to-bridge data path | **PARTIAL** | `AVFeatureBatch` preserves one IMAGE sequence per exact frame PTS and a separate AUDIO interval sequence. Full `tests/unit`: 272 passed; focused bridge/review/memory suite: 70 passed, including review validation and reviewed-claim graph/narration tests. The offline importer [`build_f10_reviewed_graphs.py`](../../../scripts/build_f10_reviewed_graphs.py) maps only `human_verified` rows into accepted VIDEO action/AUDIO transition claims with annotator and guide provenance; the direct CLI rejects blank rows, and a synthetic-row smoke check linked the real serialized VIDEO frame sequence to source PTS evidence. No human labels were present, so no reviewed output was produced. An external X-CLIP scan of 13 overlapping windows is recorded in [`video_action_sequence_xclip_tears120-140.json`](video_action_sequence_xclip_tears120-140.json). It kept a `rises_from_bed_to_standing` hypothesis after the action while raw RGB pixel-difference summaries fell; both are diagnostic only, and that hypothesis remains unverified/not passed to Qwen. The default `analyze` route still uses pooled records. |
| Cross-manifest source leakage | **PASS: validator behavior only** | `validate_manifests()` and CLI `--train/--val/--test` reject split mismatch, duplicate sample IDs, and cross-split source group/ID/SHA collisions. No real corpus exists to validate. |
| CPU prefill/decode/RSS under sustained stream load | **NOT MET** | Current-source cold-cache 60s Qwen RTSP run: capture 41.818s (0.697 capture/wall), embedding 35.099s (0.585), 548 shared-prefetch drops, 2 live Qwen captions, median observed output lag 20.758s, and 3.432GB peak process-tree RSS. L2/L3 cursors reached 25.099s before stop. Full stage/worker report: [`f10_02_followup_20261027.md`](f10_02_followup_20261027.md). This does not meet 1x. The 26 October 85s run remains a historical baseline. |
| Model/runtime licenses | **PARTIAL** | Pinned model and llama.cpp licenses are recorded in `capability_matrix.md`. No training data source has been selected, rights-reviewed, or approved for the required uses. |

## Data, baseline, and evaluation

- **Licensed source-separated train/val/held-out:** none selected; **0 source groups verified** for F10 training.
- **Independent F10 labels:** **0** delivered/verified across IMAGE, VIDEO, AUDIO, and AV. The existing 40-clip speech review pack is source-description-derived and is not independent ground truth. Do not use it for B1 or prompt tuning.
- **Schema and leakage checks:** [`av_bridge_sample_v1.schema.json`](../../../configs/schemas/av_bridge_sample_v1.schema.json) and [`validate_bridge_dataset.py`](../../../scripts/validate_bridge_dataset.py) are implemented. There is no eligible manifest to validate yet.
- **A0/B0 baseline:** the 90s `Tears of Steel` offline run is recorded in [`real_video_quality_review_b0_graph.md`](../music_quality_v2/real_video_quality_review_b0_graph.md), including every emitted L1/L2 Russian claim and all three L3 descriptions. It produced 62 L1 and 62 L2 revisions and zero newly accepted L2 details. The positive-only audio probe on the real 185–205s source interval accepts conversation in three windows; AUDIO-only L1/L2/L3 output describes conversation from source PTS 190000–205000ms but publishes no music detail. The VIDEO-only X-CLIP hypothesis at 121000–129000ms remains unverified. Full probes and media hashes are in [`f10_03_semantic_candidates_20261027.md`](f10_03_semantic_candidates_20261027.md). None of these results has independent human labels or establishes visual/music accuracy.
- **Semantic diagnosis:** [`semantic_matcher_diagnostic.md`](../semantic_matcher_diagnostic_20261026/semantic_matcher_diagnostic.md) reports 95 uncertain / 5 accepted over 100 window matches; this is label-free and cannot be treated as accuracy.
- **Registered success thresholds:** not set on independent validation data. IMAGE entity/relation, VIDEO action/identity/order, AUDIO layer/transition, AV sync, factual Russian narration, and cross-mode non-regression must each have a defined threshold before held-out evaluation.

## Resources and stop rules

- Owner authorization for prospective training is already recorded; it applies only after the gates below pass.
- The design limits the initial pilot to at most 1,000 optimizer steps or 3 epochs, whichever comes first, but **no explicit maximum GPU-hours, verified training device/VRAM, or disk budget is recorded**.
- Early-stop reasons are documented in the design, but exact validation cadence, per-mode numeric thresholds, and measured CPU 1x limits are not frozen against independent data.

## Required evidence to change NO-GO

1. Secure rights-cleared, source-separated training and validation groups plus a held-out evaluation set; record provenance and permitted use in the manifest.
2. Obtain blind human labels for all four modes, including visual entity continuity/actions/order and AV alignment; freeze per-mode metrics and non-regression criteria before evaluating held-out.
3. Independently verify the provisional X-CLIP action at source PTS 121000–129000ms and the real-film AUDIO-only scene handoff at 185000–205000ms; resolve the 13-window X-CLIP persistence failure before accepting temporal action intervals; extend supported entity/action/object and music-transition events into B0; then freeze same-source A0/B0 outputs. The current hypotheses and dialogue caption do not meet this requirement. The blind review guide, PTS-aware CSV validator, and B0 importer are [`review_guide.md`](../../review/bridge_f10_examples/review_guide.md), [`validate_f10_review_labels.py`](../../../scripts/validate_f10_review_labels.py), and [`build_f10_reviewed_graphs.py`](../../../scripts/build_f10_reviewed_graphs.py); the model failure is recorded in [`video_action_sequence_xclip_tears120-140.json`](video_action_sequence_xclip_tears120-140.json). Run the importer only after both labels validate; the current template is blank.
4. Record a bounded GPU-hours/VRAM/disk budget and validation/stop schedule in this file before training.
5. Run shape, masking, target-only loss, frozen-weight, and small train-only overfit checks, then make a measured CPU prefix/live plan. Training may start only after these entries are evidence-backed and the decision is explicitly changed to GO.

No production deployment decision is made here. A B1 model must still improve grounded factuality without unacceptable regression in visual or audio quality and meet sustained CPU 1x before production use.
