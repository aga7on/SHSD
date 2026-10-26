"""Verify the pinned llama.cpp CPU C API accepts external embeddings before text."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shsd.models.artifacts import verify_local_artifacts

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "models.lock.json"


class LlamaModelParams(ctypes.Structure):
    _fields_ = [
        ("devices", ctypes.c_void_p),
        ("tensor_buft_overrides", ctypes.c_void_p),
        ("n_gpu_layers", ctypes.c_int32),
        ("split_mode", ctypes.c_int),
        ("load_mode", ctypes.c_int),
        ("lazy_mode", ctypes.c_int),
        ("main_gpu", ctypes.c_int32),
        ("tensor_split", ctypes.POINTER(ctypes.c_float)),
        ("progress_callback", ctypes.c_void_p),
        ("progress_callback_user_data", ctypes.c_void_p),
        ("kv_overrides", ctypes.c_void_p),
        ("vocab_only", ctypes.c_bool),
        ("check_tensors", ctypes.c_bool),
        ("use_extra_bufts", ctypes.c_bool),
        ("no_host", ctypes.c_bool),
        ("no_alloc", ctypes.c_bool),
        ("load_mtp", ctypes.c_bool),
    ]


class LlamaContextParams(ctypes.Structure):
    _fields_ = [
        ("n_ctx", ctypes.c_uint32),
        ("n_batch", ctypes.c_uint32),
        ("n_ubatch", ctypes.c_uint32),
        ("n_seq_max", ctypes.c_uint32),
        ("n_rs_seq", ctypes.c_uint32),
        ("n_outputs_max", ctypes.c_uint32),
        ("n_outputs_max_per_seq", ctypes.c_uint32),
        ("n_threads", ctypes.c_int32),
        ("n_threads_batch", ctypes.c_int32),
        ("ctx_type", ctypes.c_int),
        ("rope_scaling_type", ctypes.c_int),
        ("pooling_type", ctypes.c_int),
        ("attention_type", ctypes.c_int),
        ("flash_attn_type", ctypes.c_int),
        ("rope_freq_base", ctypes.c_float),
        ("rope_freq_scale", ctypes.c_float),
        ("yarn_ext_factor", ctypes.c_float),
        ("yarn_attn_factor", ctypes.c_float),
        ("yarn_beta_fast", ctypes.c_float),
        ("yarn_beta_slow", ctypes.c_float),
        ("yarn_orig_ctx", ctypes.c_uint32),
        ("defrag_thold", ctypes.c_float),
        ("cb_eval", ctypes.c_void_p),
        ("cb_eval_user_data", ctypes.c_void_p),
        ("type_k", ctypes.c_int),
        ("type_v", ctypes.c_int),
        ("moe_cache_size", ctypes.c_size_t),
        ("abort_callback", ctypes.c_void_p),
        ("abort_callback_data", ctypes.c_void_p),
        ("embeddings", ctypes.c_bool),
        ("offload_kqv", ctypes.c_bool),
        ("no_perf", ctypes.c_bool),
        ("op_offload", ctypes.c_bool),
        ("swa_full", ctypes.c_bool),
        ("kv_unified", ctypes.c_bool),
        ("samplers", ctypes.c_void_p),
        ("n_samplers", ctypes.c_size_t),
        ("ctx_other", ctypes.c_void_p),
    ]


class LlamaBatch(ctypes.Structure):
    _fields_ = [
        ("n_tokens", ctypes.c_int32),
        ("token", ctypes.POINTER(ctypes.c_int32)),
        ("embd", ctypes.POINTER(ctypes.c_float)),
        ("pos", ctypes.POINTER(ctypes.c_int32)),
        ("n_seq_id", ctypes.POINTER(ctypes.c_int32)),
        ("seq_id", ctypes.POINTER(ctypes.POINTER(ctypes.c_int32))),
        ("logits", ctypes.POINTER(ctypes.c_int8)),
    ]


def _bind(lib: Any) -> None:
    lib.llama_backend_init.argtypes = []
    lib.llama_backend_init.restype = None
    lib.llama_backend_free.argtypes = []
    lib.llama_backend_free.restype = None
    lib.llama_model_default_params.argtypes = []
    lib.llama_model_default_params.restype = LlamaModelParams
    lib.llama_context_default_params.argtypes = []
    lib.llama_context_default_params.restype = LlamaContextParams
    lib.llama_model_load_from_file.argtypes = [ctypes.c_char_p, LlamaModelParams]
    lib.llama_model_load_from_file.restype = ctypes.c_void_p
    lib.llama_init_from_model.argtypes = [ctypes.c_void_p, LlamaContextParams]
    lib.llama_init_from_model.restype = ctypes.c_void_p
    lib.llama_model_free.argtypes = [ctypes.c_void_p]
    lib.llama_model_free.restype = None
    lib.llama_free.argtypes = [ctypes.c_void_p]
    lib.llama_free.restype = None
    lib.llama_model_get_vocab.argtypes = [ctypes.c_void_p]
    lib.llama_model_get_vocab.restype = ctypes.c_void_p
    lib.llama_model_n_embd.argtypes = [ctypes.c_void_p]
    lib.llama_model_n_embd.restype = ctypes.c_int32
    lib.llama_vocab_n_tokens.argtypes = [ctypes.c_void_p]
    lib.llama_vocab_n_tokens.restype = ctypes.c_int32
    lib.llama_tokenize.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.c_int32,
        ctypes.c_bool,
        ctypes.c_bool,
    ]
    lib.llama_tokenize.restype = ctypes.c_int32
    lib.llama_batch_init.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    lib.llama_batch_init.restype = LlamaBatch
    lib.llama_batch_free.argtypes = [LlamaBatch]
    lib.llama_batch_free.restype = None
    lib.llama_decode.argtypes = [ctypes.c_void_p, LlamaBatch]
    lib.llama_decode.restype = ctypes.c_int32
    lib.llama_get_logits_ith.argtypes = [ctypes.c_void_p, ctypes.c_int32]
    lib.llama_get_logits_ith.restype = ctypes.POINTER(ctypes.c_float)
    lib.llama_token_is_eog.argtypes = [ctypes.c_void_p, ctypes.c_int32]
    lib.llama_token_is_eog.restype = ctypes.c_bool
    lib.llama_token_to_piece.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_char_p,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_bool,
    ]
    lib.llama_token_to_piece.restype = ctypes.c_int32


def _init_batch_sequences(batch: LlamaBatch, n_tokens: int, start_pos: int) -> None:
    batch.n_tokens = n_tokens
    for index in range(n_tokens):
        batch.pos[index] = start_pos + index
        batch.n_seq_id[index] = 1
        batch.seq_id[index][0] = 0
        batch.logits[index] = 1 if index == n_tokens - 1 else 0


def _tokenize(lib: Any, vocab: Any, text: str) -> list[int]:
    encoded = text.encode("utf-8")
    required = lib.llama_tokenize(vocab, encoded, len(encoded), None, 0, True, True)
    if required >= 0:
        raise RuntimeError(f"expected token count query to return negative size, got {required}")
    capacity = -required
    token_buffer = (ctypes.c_int32 * capacity)()
    count = lib.llama_tokenize(vocab, encoded, len(encoded), token_buffer, capacity, True, True)
    if count < 0:
        raise RuntimeError(f"tokenization failed with code {count}")
    return list(token_buffer[:count])


def _decode_batch(lib: Any, context: Any, batch: LlamaBatch, *, label: str) -> None:
    code = lib.llama_decode(context, batch)
    if code != 0:
        raise RuntimeError(f"llama_decode({label}) returned {code}")


def _run(threads: int) -> dict[str, Any]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    model_info = lock["models"]["qwen3_0_6b"]
    runtime_info = lock["runtimes"]["llama_cpp"]
    verified = verify_local_artifacts("qwen3_0_6b", model_info, ROOT / "models")
    bin_dir = ROOT / "models" / "runtimes" / "llama_cpp" / runtime_info["version"] / "bin"
    model_path = ROOT / "models" / "qwen3_0_6b" / model_info["file"]
    dll_path = bin_dir / "llama.dll"
    if not dll_path.is_file():
        raise FileNotFoundError(dll_path)
    if os.name == "nt":
        dll_handle = os.add_dll_directory(str(bin_dir))
    else:
        dll_handle = None
    ggml = ctypes.CDLL(str(bin_dir / "ggml.dll"))
    ggml.ggml_backend_load_all_from_path.argtypes = [ctypes.c_char_p]
    ggml.ggml_backend_load_all_from_path.restype = None
    lib = ctypes.CDLL(str(dll_path))
    _bind(lib)

    stderr_fd = os.dup(2)
    null_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null_fd, 2)
    model = None
    context = None
    try:
        ggml.ggml_backend_load_all_from_path(os.fsencode(bin_dir))
        lib.llama_backend_init()
        started = time.perf_counter()
        model_params = lib.llama_model_default_params()
        model_params.n_gpu_layers = 0
        model = lib.llama_model_load_from_file(os.fsencode(model_path), model_params)
        if not model:
            raise RuntimeError("llama_model_load_from_file returned NULL")
        model_load_ms = (time.perf_counter() - started) * 1000
        embedding_dim = int(lib.llama_model_n_embd(model))
        vocab = lib.llama_model_get_vocab(model)
        vocab_size = int(lib.llama_vocab_n_tokens(vocab))

        context_params = lib.llama_context_default_params()
        context_params.n_ctx = 512
        context_params.n_batch = 128
        context_params.n_ubatch = 128
        context_params.n_threads = threads
        context_params.n_threads_batch = threads
        context = lib.llama_init_from_model(model, context_params)
        if not context:
            raise RuntimeError("llama_init_from_model returned NULL")

        # The F10 projector output has Qwen's native hidden width. Deterministic
        # small values validate transport and decode only; they are not a trained prefix.
        prefix_tokens = 4
        prefix_values = (ctypes.c_float * (prefix_tokens * embedding_dim))(
            *[0.001 * ((i % 17) - 8) for i in range(prefix_tokens * embedding_dim)]
        )
        prefix_batch = lib.llama_batch_init(prefix_tokens, embedding_dim, 1)
        if not prefix_batch.embd:
            raise RuntimeError("llama_batch_init did not allocate external embedding storage")
        ctypes.memmove(
            prefix_batch.embd,
            ctypes.addressof(prefix_values),
            ctypes.sizeof(prefix_values),
        )
        _init_batch_sequences(prefix_batch, prefix_tokens, 0)
        prefix_started = time.perf_counter()
        _decode_batch(lib, context, prefix_batch, label="external prefix")
        prefix_decode_ms = (time.perf_counter() - prefix_started) * 1000
        lib.llama_batch_free(prefix_batch)

        prompt = "Answer briefly: music."
        prompt_tokens = _tokenize(lib, vocab, prompt)
        text_batch = lib.llama_batch_init(len(prompt_tokens), 0, 1)
        if not text_batch.token:
            raise RuntimeError("llama_batch_init did not allocate token storage")
        _init_batch_sequences(text_batch, len(prompt_tokens), prefix_tokens)
        for index, token in enumerate(prompt_tokens):
            text_batch.token[index] = token
        prompt_started = time.perf_counter()
        _decode_batch(lib, context, text_batch, label="text after external prefix")
        prompt_decode_ms = (time.perf_counter() - prompt_started) * 1000
        lib.llama_batch_free(text_batch)

        generated_tokens: list[int] = []
        for step in range(4):
            logits = lib.llama_get_logits_ith(context, -1)
            if not logits:
                raise RuntimeError("llama_get_logits_ith returned NULL after prefix and prompt")
            token = max(range(vocab_size), key=lambda idx: logits[idx])
            generated_tokens.append(int(token))
            if lib.llama_token_is_eog(vocab, token):
                break
            next_batch = lib.llama_batch_init(1, 0, 1)
            _init_batch_sequences(next_batch, 1, prefix_tokens + len(prompt_tokens) + step)
            next_batch.token[0] = token
            _decode_batch(lib, context, next_batch, label=f"generated token {step}")
            lib.llama_batch_free(next_batch)

        return {
            "status": "passed",
            "runtime_version": runtime_info["version"],
            "model_repo": model_info["repo_id"],
            "model_revision": model_info["revision"],
            "model_quantization": model_info["quantization"],
            "verified_files": verified,
            "execution": "CPU",
            "threads": threads,
            "model_load_ms": round(model_load_ms, 2),
            "llama_model_n_embd": embedding_dim,
            "vocab_size": vocab_size,
            "external_prefix": {
                "shape": [prefix_tokens, embedding_dim],
                "dtype": "float32",
                "values": "deterministic small probe values; untrained, no quality claim",
                "decode_ms": round(prefix_decode_ms, 2),
            },
            "text_after_prefix": {
                "token_count": len(prompt_tokens),
                "decode_ms": round(prompt_decode_ms, 2),
            },
            "greedy_decode_tokens": generated_tokens,
            "generation_status": "passed" if generated_tokens else "failed",
            "scope": (
                "Real GGUF checkpoint accepted external token embeddings through "
                "llama_batch.embd, followed by ordinary text tokens and CPU decode. "
                "This verifies API/deployment shape only, not a learned projector "
                "or useful conditioning quality."
            ),
        }
    finally:
        if context:
            lib.llama_free(context)
        if model:
            lib.llama_model_free(model)
        lib.llama_backend_free()
        os.dup2(stderr_fd, 2)
        os.close(stderr_fd)
        os.close(null_fd)
        if dll_handle is not None:
            dll_handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "benchmarks" / "reports" / "bridge_f10" / "llama_cpp_prefix_smoke.json",
    )
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    report = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "task": "F10.01",
        "host": {"os": platform.platform(), "cpu": platform.processor()},
        "result": _run(args.threads),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    serialized_report = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.report.write_text(serialized_report, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
