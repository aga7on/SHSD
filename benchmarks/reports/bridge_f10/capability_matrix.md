# F10.01 capability matrix — EmbeddingGemma 2 → Qwen3-0.6B

Date: 2026-10-26 · host: Windows 11, AMD64 Family 26 Model 68 Stepping 0 · CPU-only, 4 threads.

## Decision

**The tensor/API path for a trainable bridge is technically feasible on the pinned CPU runtime.** EmbeddingGemma 2 exposes variable-length token embeddings in all four input modes; the installed Qwen3 GGUF accepts an external 4×1024 embedding prefix through llama.cpp, then accepts ordinary text tokens and decodes on CPU. This is an API/deployment-shape result. It does not show that random projector outputs produce useful descriptions, that a learned projector will improve quality, or that the current stream meets 1× realtime.

**Training status: NO-GO pending F10.02 data/evaluation/budget evidence.** The owner has already authorized prospective training after a documented GO; no additional permission is needed. The production `EmbeddingProvider` exposes opt-in unpooled sequence features, masks, token IDs, exact sampled frame PTS, and video metadata. A typed `AVFeatureBatch` now groups per-frame image sequences with their exact PTS and a separate audio interval; it is implemented but not yet connected to the default `analyze` or EventGraph/B0 input. The B0 event graph consumes timeline claims and safe start-order edges, but does not yet infer visual entities/actions or music layers. Neither adapter integration nor learned quality/realtime is demonstrated.

## Reproduction

Model revisions and artifacts are verified against `models.lock.json` before each run.

```powershell
.\.venv\Scripts\python.exe scripts\smoke_bridge_api.py --threads 4
.\.venv\Scripts\python.exe scripts\smoke_embedding_sequence_provider.py --threads 4
.\.venv\Scripts\python.exe scripts\smoke_models.py --model qwen3_0_6b --threads 4 --max-tokens 48 --offline --report benchmarks\reports\bridge_f10\qwen_text_smoke.json
.\.venv\Scripts\python.exe scripts\smoke_llama_cpp_prefix.py --threads 4
```

Results: exit code 0 for all four commands. Raw JSON: [api_smoke.json](api_smoke.json), [production_sequence_smoke.json](production_sequence_smoke.json), [qwen_text_smoke.json](qwen_text_smoke.json), [llama_cpp_prefix_smoke.json](llama_cpp_prefix_smoke.json).

Environment: Python 3.14.6, PyTorch 2.14.0+cpu, Sentence Transformers 6.2.0, Transformers 5.20.2; network disabled in `smoke_bridge_api.py`. EmbeddingGemma revision `914f7f89142e33e77833254d9c9b90c3cef7303b`, Qwen3 GGUF revision `13ac06624948e4d8589cb4b6f90100837342fcb8` (`Q8_0`), llama.cpp `b11886` (build 11886, commit `2280f0fd1`). Local model hashes matched `models.lock.json`.

## Matrix

| Capability | Evidence | Status / limitation |
|---|---|---|
| IMAGE input to EmbeddingGemma | Pooled output `[768]`; pre-pooling token embeddings `[1,264,768]`; image patch positions present; 2,672 ms in this single CPU run | **Supported.** Synthetic image fixture, not visual-quality evaluation. |
| AUDIO input to EmbeddingGemma | Five-second, 80,000-sample PyAV waveform; pooled `[768]`; pre-pooling token embeddings `[1,129,768]`; 170 ms | **Supported.** Fixture contains Russian speech; this is not a music-classification result. |
| VIDEO input to EmbeddingGemma | Four frames sampled at source PTS 0/1300/2500/3800 ms; pooled `[768]`; pre-pooling tokens `[1,517,768]`; timestamp markers `00:00`–`00:03`; 4,125 ms | **Supported with explicit metadata.** Timestamp text is injected only when `add_timestamps=True`; `video_position_ids` are spatial patch positions, not source timestamps. |
| Synchronous AV input to EmbeddingGemma | Same five-second audio plus those four PTS-sampled frames; pooled `[768]`; pre-pooling tokens `[1,644,768]`; audio and video markers coexist; 3,918 ms | **Supported at encoder API level.** Does not prove the pooled vector preserves alignment or causality. |
| EmbeddingGemma sequence features before pooling | Forward hook and production `SequenceFeatureRecord` capture finite token embeddings, masks, token IDs, modality positions, and video metadata | **Supported by production opt-in APIs.** This proves transport only, not semantic quality or token-to-frame alignment. |
| Production-provider sequence features | `smoke_embedding_sequence_provider.py --threads 4`; IMAGE `[268,768]`, AUDIO `[129,768]`, VIDEO `[517,768]`, AV `[644,768]`; masks, IDs, modality positions, and exact sampled PTS | **Supported by opt-in APIs.** `analyze` and the claim graph still consume pooled L1/L2 claims; sequence features are not wired into EventGraph/B0. |
| Qwen3 `inputs_embeds` behavior | Transformers 5.20.2 synthetic `Qwen3ForCausalLM`: forward, gradient into a prefix while weights are frozen, and `generate(inputs_embeds=...)` all passed | **Synthetic API only.** The real checkpoint is not loaded into Transformers. |
| Qwen3 GGUF CPU external-prefix transport | Real Q8_0 checkpoint reports hidden width 1024; `llama_batch.embd` accepted a deterministic `[4,1024]` external prefix; ordinary tokens followed; greedy decode passed. Prefix decode 86 ms, five text tokens 25 ms, four generated tokens. | **Supported in pinned llama.cpp C API on CPU.** Values are untrained probe inputs; no useful-conditioning claim. |
| Plain Qwen3 GGUF text generation | Existing offline smoke passed on CPU; 48-token cap; 1,173 ms in one run | **Supported.** Text-only functionality, not bridge quality. |
| Provider video PTS preservation | `encode_video_features` and `encode_joint_features` preserve PTS `[0,1300,2500,3800]` ms and pass frame indices `[0,13,25,38]`, FPS, duration and frame count | **Supported by opt-in API.** Token-to-frame span alignment and default `analyze` integration remain open. |
| PTS-preserving B1 batch interface | [`src/shsd/bridge/features.py`](../../../src/shsd/bridge/features.py) groups individual IMAGE sequences by exact source PTS and interval AUDIO features, with modality checks and model provenance | **Implemented, not smoke-tested or integrated.** It deliberately avoids guessing token/frame spans in flattened VIDEO output; per-audio-token timestamps remain unavailable. |
| Default analyze token-level bridge input | Existing analysis still uses pooled `encode_frame`/`encode_audio`; B0 graph consumes the resulting timeline claims | **Not integrated.** Visual action/entity nodes and source feature injection into B0 remain open. |
| F10 data manifest and rights/leakage validator | [`av_bridge_sample_v1.schema.json`](../../../configs/schemas/av_bridge_sample_v1.schema.json), [`validate_bridge_dataset.py`](../../../scripts/validate_bridge_dataset.py) | **Implemented, no corpus to validate.** No rights-cleared, human-verified source-separated samples are recorded yet. |
| Sustained 1× CPU AV stream | No end-to-end stream benchmark here; isolated 5s VIDEO/AV embedding calls took about 4s, excluding the Qwen stage | **Not met / not measured.** These runs do not demonstrate sustained capture, queue stability, or output cadence. |

## Recommended B1 tensor path

1. Keep EmbeddingGemma 2 and Qwen3 frozen. Use the provider's opt-in sequence methods to read `token_embeddings`, attention masks, token IDs, and timestamp metadata before mean pooling. Each sample carries a mode (`IMAGE`, `VIDEO`, `AUDIO`, or `AV`), source-time metadata, and independent modality masks.
2. Add small trainable projections from the 768-wide encoder sequence to Qwen's actual 1024-wide input space. Use a bounded resampler so patch/audio token counts fit a fixed context budget. Add explicit modality and temporal-position embeddings; keep original PTS and source evidence alongside the tensors. AV uses both streams and a fusion/resampling block; single-modality batches mask the missing branch rather than inventing null content.
3. Feed the projected sequence as the initial Qwen soft prefix through the verified llama.cpp external-embedding batch API; continue with ordinary prompt/target tokens. The Python `inputs_embeds` route is a training/API prototype only; production inference should use the tested native CPU path or another measured runtime.
4. Train only the projector/resampler in B1. Use target-only teacher-forced next-token loss for grounded structured claims plus Russian caption. Keep IMAGE-only spatial description, VIDEO-only temporal action/order, AUDIO-only musical layers/transitions, and AV grounding as separate evaluation slices. Add alignment/coverage terms only after an ablation identifies a labeled failure they address; never fit weights on held-out examples.
5. Run B0 (typed EventGraph→text→Qwen) first. B1 is allowed only after licensed paired training data, source-separated train/val/held-out splits, independent F7.03 labels, baseline metrics, bounded GPU budget, and stop criteria are recorded in `F10-GO.md`. The existing 40-clip speech-presence review set is not a substitute for the required visual/music/AV evaluation set.

## Source and interpretation

- The native external-embedding batch is documented by the pinned [llama.cpp `llama.h` at b11886](https://raw.githubusercontent.com/ggml-org/llama.cpp/b11886/include/llama.h): `llama_batch.embd` supplies external token vectors when `token` is null, and `llama_decode` processes the batch.
- EmbeddingGemma's installed Transformer module declares `module_output_name: token_embeddings`; the smoke hook verifies this behavior locally for the pinned model artifacts. The official [EmbeddingGemma model card](https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2) and [multimodal Sentence Transformers guide](https://ai.google.dev/gemma/docs/embeddinggemma/multimodal-embeddinggemma-with-sentence-transformers) describe the supported image/audio/video inputs and pooled output.
- Model/revision and license metadata are pinned in `models.lock.json`. This audit does not review any new training corpus license because no F10 training corpus has been selected.
