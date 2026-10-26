"""Bounded local Qwen narration over accepted, timestamped evidence only."""

from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from shsd.models.artifacts import verify_local_artifacts

PROMPT_VERSION = "narrator-ru-v1"
DEFAULT_MAX_TOKENS = 128
DEFAULT_TIMEOUT_SECONDS = 45.0
DEFAULT_MAX_INPUT_CHARS = 4_096


@dataclass(frozen=True, slots=True)
class NarrationEventRef:
    event_id: str
    revision: int

    def __post_init__(self) -> None:
        if not self.event_id or self.revision < 1:
            raise ValueError("event_id and positive revision are required")


@dataclass(frozen=True, slots=True)
class NarrationClaim:
    claim_id: str
    event_id: str
    revision: int
    start_ms: int
    end_ms: int
    text_ru: str
    decision: Literal["accepted"] = "accepted"
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.claim_id or not self.event_id or self.revision < 1:
            raise ValueError("claim, event, and revision IDs are required")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("claim interval must satisfy 0 <= start_ms < end_ms")
        if not self.text_ru.strip():
            raise ValueError("accepted claims require Russian display text")
        if self.decision != "accepted":
            raise ValueError("the narrator accepts only accepted claims")
        if not self.evidence_refs:
            raise ValueError("accepted claims require evidence references")


@dataclass(frozen=True, slots=True)
class NarrationASRQuote:
    segment_id: str
    start_ms: int
    end_ms: int
    text: str
    quality: float
    source: str

    def __post_init__(self) -> None:
        if not self.segment_id or not self.source or not self.text.strip():
            raise ValueError("ASR segment ID, source, and text are required")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("ASR interval must satisfy 0 <= start_ms < end_ms")
        if not 0.0 <= self.quality <= 1.0:
            raise ValueError("ASR quality must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class NarrationRequest:
    stream_id: str
    epoch: int
    event_refs: tuple[NarrationEventRef, ...]
    claims: tuple[NarrationClaim, ...]
    asr_quotes: tuple[NarrationASRQuote, ...] = ()
    state: dict[str, object] | None = None
    delta: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if not self.stream_id or self.epoch < 0:
            raise ValueError("stream_id and non-negative epoch are required")
        if not self.event_refs:
            raise ValueError("narration requires at least one event reference")
        if not self.claims and not self.asr_quotes:
            raise ValueError("narration requires an accepted claim or ASR quote")
        if len({item.event_id for item in self.event_refs}) != len(self.event_refs):
            raise ValueError("event references must be unique")
        if len({item.claim_id for item in self.claims}) != len(self.claims):
            raise ValueError("claim IDs must be unique")
        if len({item.segment_id for item in self.asr_quotes}) != len(self.asr_quotes):
            raise ValueError("ASR segment IDs must be unique")
        event_revisions = {(item.event_id, item.revision) for item in self.event_refs}
        if any((item.event_id, item.revision) not in event_revisions for item in self.claims):
            raise ValueError("every claim must reference a supplied event revision")

    @property
    def time_range(self) -> tuple[int, int]:
        intervals = [
            (claim.start_ms, claim.end_ms) for claim in self.claims
        ] + [(quote.start_ms, quote.end_ms) for quote in self.asr_quotes]
        return min(item[0] for item in intervals), max(item[1] for item in intervals)

    @property
    def source_ids(self) -> frozenset[str]:
        return frozenset(
            [claim.claim_id for claim in self.claims]
            + [quote.segment_id for quote in self.asr_quotes]
        )

    def facts_payload(self) -> dict[str, object]:
        return {
            "stream_id": self.stream_id,
            "epoch": self.epoch,
            "event_revisions": [asdict(item) for item in self.event_refs],
            "accepted_claims": [asdict(item) for item in self.claims],
            "asr_quotes": [asdict(item) for item in self.asr_quotes],
            "state": self.state,
            "delta": self.delta,
            "time_range": {"start_ms": self.time_range[0], "end_ms": self.time_range[1]},
        }


@dataclass(frozen=True, slots=True)
class NarrationResponse:
    caption_ru: str
    used_claim_ids: tuple[str, ...]
    start_ms: int
    end_ms: int
    warnings: tuple[str, ...] = ()
    new_unsupported_claims: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.caption_ru, str)
            or not self.caption_ru.strip()
            or len(self.caption_ru) > 2000
        ):
            raise ValueError("caption_ru must contain between 1 and 2000 characters")
        if (
            not self.used_claim_ids
            or any(not isinstance(item, str) or not item for item in self.used_claim_ids)
            or len(set(self.used_claim_ids)) != len(self.used_claim_ids)
        ):
            raise ValueError("used_claim_ids must be non-empty and unique")
        if (
            type(self.start_ms) is not int
            or type(self.end_ms) is not int
            or self.start_ms < 0
            or self.end_ms <= self.start_ms
        ):
            raise ValueError("caption interval must satisfy 0 <= start_ms < end_ms")
        if len(self.warnings) > 8 or any(
            not isinstance(item, str) or len(item) > 500 for item in self.warnings
        ):
            raise ValueError("warnings must contain at most eight strings up to 500 characters")

    def to_dict(self) -> dict[str, object]:
        return {
            "caption_ru": self.caption_ru,
            "used_claim_ids": list(self.used_claim_ids),
            "new_unsupported_claims": list(self.new_unsupported_claims),
            "time_range": {"start_ms": self.start_ms, "end_ms": self.end_ms},
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class NarrationResult:
    response: NarrationResponse
    status: Literal["generated", "fallback"]
    model_revision: str
    prompt_version: str
    event_revisions: tuple[NarrationEventRef, ...]
    latency_ms: float
    backend: Literal["qwen", "template"] = "qwen"
    generated_token_count: int | None = None
    generation_ms: float | None = None
    generation_tokens_per_second: float | None = None

    def __post_init__(self) -> None:
        if not self.model_revision or not self.prompt_version:
            raise ValueError("model_revision and prompt_version are required")
        if self.status not in {"generated", "fallback"}:
            raise ValueError("unsupported narration status")
        if self.backend not in {"qwen", "template"}:
            raise ValueError("unsupported narration backend")
        if not self.event_revisions or len(
            {item.event_id for item in self.event_revisions}
        ) != len(self.event_revisions):
            raise ValueError("event revisions must be present and unique")
        if (
            isinstance(self.latency_ms, bool)
            or not isinstance(self.latency_ms, (int, float))
            or not math.isfinite(self.latency_ms)
            or self.latency_ms < 0
        ):
            raise ValueError("latency_ms must be a finite non-negative number")
        if self.generated_token_count is not None and (
            type(self.generated_token_count) is not int or self.generated_token_count < 0
        ):
            raise ValueError("generated_token_count must be a non-negative integer or None")
        if self.generation_ms is not None and (
            isinstance(self.generation_ms, bool)
            or not isinstance(self.generation_ms, (int, float))
            or not math.isfinite(self.generation_ms)
            or self.generation_ms < 0
        ):
            raise ValueError("generation_ms must be finite and non-negative or None")
        if self.generation_tokens_per_second is not None and (
            isinstance(self.generation_tokens_per_second, bool)
            or not isinstance(self.generation_tokens_per_second, (int, float))
            or not math.isfinite(self.generation_tokens_per_second)
            or self.generation_tokens_per_second < 0
        ):
            raise ValueError("generation_tokens_per_second must be finite and non-negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "record_type": "caption",
            **self.response.to_dict(),
            "status": self.status,
            "backend": self.backend,
            "model_revision": self.model_revision,
            "prompt_version": self.prompt_version,
            "event_revisions": [asdict(item) for item in self.event_revisions],
            "latency_ms": self.latency_ms,
            "generated_token_count": self.generated_token_count,
            "generation_ms": self.generation_ms,
            "tokens_per_second": round(self.generation_tokens_per_second, 3)
            if self.generation_tokens_per_second is not None
            else round(self.generated_token_count / (self.generation_ms / 1000), 3)
            if self.generated_token_count is not None
            and self.generation_ms is not None
            and self.generation_ms > 0
            else None,
        }


class QwenNarrator:
    """Run one bounded, non-thinking Qwen turn through the pinned llama.cpp CLI."""

    def __init__(
        self,
        model: dict[str, Any],
        models_dir: Path,
        repo_root: Path,
        *,
        threads: int = 4,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_input_chars: int = DEFAULT_MAX_INPUT_CHARS,
    ) -> None:
        if threads < 1:
            raise ValueError("threads must be positive")
        if not 16 <= max_tokens <= 256:
            raise ValueError("max_tokens must be between 16 and 256")
        if not 1.0 <= timeout_seconds <= 120.0:
            raise ValueError("timeout_seconds must be between 1 and 120")
        if not 256 <= max_input_chars <= DEFAULT_MAX_INPUT_CHARS:
            raise ValueError(
                f"max_input_chars must be between 256 and {DEFAULT_MAX_INPUT_CHARS}"
            )
        self.model = model
        self.model_revision = str(model["revision"])
        verified_files = verify_local_artifacts("qwen3_0_6b", model, models_dir)
        self.model_path = models_dir / "qwen3_0_6b" / str(model["file"])
        self.llama_cli = (
            models_dir / "runtimes" / "llama_cpp" / "b11886" / "bin" / "llama-cli.exe"
        )
        if str(self.llama_cli) not in verified_files and not self.llama_cli.is_file():
            raise FileNotFoundError(
                f"llama.cpp executable is missing: {self.llama_cli}; "
                "fetch it with scripts/download_models.py --runtime llama_cpp"
            )
        self.prompt_path = repo_root / "configs" / "prompts" / "narrator_ru_v1.jinja"
        self.schema_path = repo_root / "configs" / "schemas" / "narration_v1.schema.json"
        self.template_path = repo_root / "configs" / "qwen3_nonthinking.jinja"
        for path in (self.prompt_path, self.schema_path, self.template_path):
            if not path.is_file():
                raise FileNotFoundError(f"narrator resource is missing: {path}")
        self.threads = threads
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.max_input_chars = max_input_chars

    def _build_prompt(self, request: NarrationRequest) -> str:
        facts = json.dumps(request.facts_payload(), ensure_ascii=False, sort_keys=True)
        template = self.prompt_path.read_text(encoding="utf-8")
        prompt = template.replace("{{facts_json}}", facts)
        if "{{facts_json}}" in prompt:
            raise ValueError("narrator prompt template contains an unresolved placeholder")
        if len(prompt) > self.max_input_chars:
            raise ValueError(
                f"narration chunk is {len(prompt)} characters; limit is {self.max_input_chars}"
            )
        return prompt

    def _command(self, prompt: str, output_path: Path) -> list[str]:
        return [
            str(self.llama_cli),
            "--model",
            str(self.model_path),
            "--prompt",
            prompt,
            "--chat-template-file",
            str(self.template_path),
            "--jinja",
            "--single-turn",
            "--no-display-prompt",
            "--simple-io",
            "--perf",
            "--show-timings",
            "--output-file",
            str(output_path),
            "--threads",
            str(self.threads),
            "--ctx-size",
            "2048",
            "--predict",
            str(self.max_tokens),
            "--temp",
            "0",
            "--top-k",
            "1",
            "--seed",
            "7",
        ]

    @staticmethod
    def _extract_caption(output: str) -> str:
        text = output
        assistant_markers = list(re.finditer(r"(?:^|\n)Assistant:\s*", text, re.IGNORECASE))
        if assistant_markers:
            text = text[assistant_markers[-1].end() :]
        elif "\nUser:" in text or "\nAssistant:" in text:
            raise ValueError("Qwen transcript did not contain an assistant answer")
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.split(r"\r?\n\s*(?:\[ Prompt:|Exiting\.\.\.)", text, maxsplit=1)[0]
        text = text.strip().strip("`\"'").strip()
        if (
            not text
            or len(text) > 2000
            or "<think>" in text
            or "```" in text
            or not any("\u0400" <= char <= "\u04ff" for char in text)
        ):
            raise ValueError("Qwen output is not a short Russian caption")
        return text

    @staticmethod
    def _parse_generation_metrics(
        output: str,
    ) -> tuple[int | None, float | None, float | None]:
        """Read generated-token throughput and, when present, count and duration."""
        match = re.search(
            r"(?:eval|generation) time\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*ms\s*/\s*"
            r"([0-9]+)\s*tokens\b",
            output,
            flags=re.IGNORECASE,
        )
        if match is not None:
            generated_tokens = int(match.group(2))
            generation_ms = float(match.group(1))
            return (
                generated_tokens,
                generation_ms,
                round(generated_tokens / (generation_ms / 1000), 3)
                if generation_ms > 0
                else None,
            )
        rate_match = re.search(
            r"Generation:\s*([0-9]+(?:\.[0-9]+)?)\s*t/s",
            output,
            flags=re.IGNORECASE,
        )
        return None, None, float(rate_match.group(1)) if rate_match is not None else None

    @staticmethod
    def _has_supported_vocabulary(caption: str, request: NarrationRequest) -> bool:
        """Reject generated content words that do not occur in approved source text."""
        source_text = [claim.text_ru for claim in request.claims]
        source_text.extend(quote.text for quote in request.asr_quotes)

        def normalize(value: str) -> str:
            return value.casefold().replace("ё", "е")

        supported = {
            normalize(token)
            for text in source_text
            for token in re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", text)
        }
        generated = {
            normalize(token)
            for token in re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", caption)
        }
        negation = {"не", "нет", "без", "ни", "никогда", "никто", "ничто"}
        source_negations = sum(
            normalize(token) in negation
            for text in source_text
            for token in re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", text)
        )
        generated_negations = sum(
            normalize(token) in negation
            for token in re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", caption)
        )
        return (
            bool(generated)
            and generated.issubset(supported)
            and generated_negations == source_negations
        )

    @staticmethod
    def _fallback(request: NarrationRequest, warning: str) -> NarrationResponse:
        texts = [claim.text_ru.strip() for claim in request.claims]
        texts.extend(f"Цитата: «{quote.text.strip()}»" for quote in request.asr_quotes)
        return NarrationResponse(
            caption_ru=" ".join(texts),
            used_claim_ids=tuple(sorted(request.source_ids)),
            start_ms=request.time_range[0],
            end_ms=request.time_range[1],
            warnings=(warning,),
        )

    def narrate(self, request: NarrationRequest) -> NarrationResult:
        """Generate a caption; timeouts and invalid output use a source-only fallback."""
        prompt = self._build_prompt(request)
        started = time.perf_counter()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as output_file:
            output_path = Path(output_file.name)
        status: Literal["generated", "fallback"] = "fallback"
        generated_token_count: int | None = None
        generation_ms: float | None = None
        generation_tokens_per_second: float | None = None
        try:
            completed = subprocess.run(
                self._command(prompt, output_path),
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
            output_chunks = []
            for output in (completed.stdout, completed.stderr):
                if isinstance(output, bytes):
                    output_chunks.append(output.decode("utf-8", errors="replace"))
                elif isinstance(output, str):
                    output_chunks.append(output)
            (
                generated_token_count,
                generation_ms,
                generation_tokens_per_second,
            ) = self._parse_generation_metrics("\n".join(output_chunks))
            caption = self._extract_caption(output_path.read_text(encoding="utf-8"))
            if not self._has_supported_vocabulary(caption, request):
                response = self._fallback(request, "unsupported_terms")
                status = "fallback"
            else:
                response = NarrationResponse(
                    caption_ru=caption,
                    used_claim_ids=tuple(sorted(request.source_ids)),
                    start_ms=request.time_range[0],
                    end_ms=request.time_range[1],
                )
                status = "generated"
        except subprocess.TimeoutExpired:
            response = self._fallback(request, "qwen_timeout")
            status = "fallback"
        except (OSError, subprocess.CalledProcessError, ValueError):
            response = self._fallback(request, "qwen_output_invalid")
            status = "fallback"
        finally:
            output_path.unlink(missing_ok=True)
        latency_ms = (time.perf_counter() - started) * 1000
        return NarrationResult(
            response=response,
            status=status,
            model_revision=self.model_revision,
            prompt_version=PROMPT_VERSION,
            event_revisions=request.event_refs,
            latency_ms=round(latency_ms, 3),
            backend="qwen",
            generated_token_count=generated_token_count,
            generation_ms=generation_ms,
            generation_tokens_per_second=generation_tokens_per_second,
        )


class TemplateNarrator:
    """Source-only caption baseline with no model load or generated facts."""

    model_revision = "template-source-only-v1"
    prompt_version = "template-source-only-v1"

    def narrate(self, request: NarrationRequest) -> NarrationResult:
        started = time.perf_counter()
        response = QwenNarrator._fallback(request, "template_baseline")
        return NarrationResult(
            response=response,
            status="fallback",
            model_revision=self.model_revision,
            prompt_version=self.prompt_version,
            event_revisions=request.event_refs,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            backend="template",
        )
