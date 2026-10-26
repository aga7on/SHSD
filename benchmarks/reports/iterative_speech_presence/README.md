# Iterative `speech_presence` A/B

## Setup

- EmbeddingGemma 2: `google/embeddinggemma-2`, revision `914f7f89142e33e77833254d9c9b90c3cef7303b`, local files only, CPU, 4 threads.
- Qwen3-0.6B: `ggml-org/Qwen3-0.6B-GGUF`, Q8_0, local llama.cpp build `b11886`, CPU, 4 threads.
- Runtime: Sentence Transformers 6.2.0, Transformers 5.20.2, Hugging Face Hub 1.33.0, PyTorch 2.14.0+cpu.
- Axis: `speech_presence`; policy: cosine >= 0.60 and margin >= 0.05.
- Four synthetic local fixtures, six 5-second-or-shorter windows, all labeled from their generation recipe and `tests/fixtures/manifest.json`. They are engineering fixtures, not natural speech or a representative quality corpus.
- `iterations.jsonl` contains the paired baseline and iterative rows. Per-source analysis JSONL files preserve the run output; `labels.jsonl` records the expected axis decision and rationale.

## Result

`evaluation.json` reports 6/6 matched windows and no unmatched labels. Baseline and iterative scores are identical: 1/6 correct over all windows (16.7% accuracy), 1/6 coverage (16.7%), and 1/1 correct among accepted claims. Qwen made four proposal attempts totaling 13,537.161 ms; EmbeddingGemma accepted zero generated candidates. Every attempted row kept the baseline decision.

The proposal output was also inspected for one uncertain speech window. Qwen returned fenced JSON with repeated existing candidates and entries missing `text_ru`; the strict parser correctly rejected all of them. This run shows no benefit for the tested axis and fixtures. Keep iterative prompting opt-in. This result does not measure quality on natural speech, music, or environmental audio; that broader labeled evaluation remains open.

`asr_embedding_smoke.jsonl` is a separate compatibility pass through the actual analyzer with both EmbeddingGemma and GigaAM enabled. It produced a partial/final transcript, no ASR queue drops or failures, and completed L1 coverage. GigaAM's pinned Transformers-4-era model code needs a local CPU-initialization shim under Transformers 5; this smoke verifies that combination, not transcript accuracy.
