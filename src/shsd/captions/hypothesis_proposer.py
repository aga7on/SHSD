"""Strict, bounded Qwen proposals for one selected semantic axis."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shsd.models.artifacts import verify_local_artifacts
from shsd.semantic.hypotheses import HypothesisAxis, HypothesisCandidate
from shsd.semantic.matcher import RankedCandidate

PROMPT_VERSION = "hypothesis-refiner-v1"


@dataclass(frozen=True, slots=True)
class ProposalResult:
    candidates: tuple[HypothesisCandidate, ...]
    latency_ms: float


class QwenHypothesisProposer:
    """Return candidate strings only; it never decides whether a claim is true."""

    def __init__(
        self,
        model: dict[str, Any],
        models_dir: Path,
        repo_root: Path,
        *,
        threads: int = 4,
        max_candidates: int = 6,
        timeout_seconds: float = 10.0,
    ) -> None:
        if threads < 1 or not 1 <= max_candidates <= 6:
            raise ValueError("threads must be positive and max_candidates must be between 1 and 6")
        if not 1.0 <= timeout_seconds <= 30.0:
            raise ValueError("timeout_seconds must be between 1 and 30")
        verified_files = verify_local_artifacts("qwen3_0_6b", model, models_dir)
        self.model_revision = str(model["revision"])
        self.model_path = models_dir / "qwen3_0_6b" / str(model["file"])
        self.llama_cli = (
            models_dir / "runtimes" / "llama_cpp" / "b11886" / "bin" / "llama-cli.exe"
        )
        if str(self.llama_cli) not in verified_files and not self.llama_cli.is_file():
            raise FileNotFoundError(f"llama.cpp executable is missing: {self.llama_cli}")
        self.prompt_path = repo_root / "configs" / "prompts" / "hypothesis_refiner_v1.jinja"
        self.template_path = repo_root / "configs" / "qwen3_nonthinking.jinja"
        if not self.prompt_path.is_file() or not self.template_path.is_file():
            raise FileNotFoundError("hypothesis refiner prompt or Qwen chat template is missing")
        self.threads = threads
        self.max_candidates = max_candidates
        self.timeout_seconds = timeout_seconds

    def _build_prompt(
        self, axis: HypothesisAxis, top_candidates: tuple[RankedCandidate, ...]
    ) -> str:
        axis_payload = {
            "axis_id": axis.axis_id,
            "modality": axis.modality,
            "mutually_exclusive": axis.mutually_exclusive,
            "existing_candidates": [
                {"id": item.candidate_id, "text_en": item.text_en}
                for item in axis.candidates
            ],
        }
        ranked_payload = [
            {
                "candidate_id": item.candidate_id,
                "text_en": next(
                    candidate.text_en
                    for candidate in axis.candidates
                    if candidate.candidate_id == item.candidate_id
                ),
                "raw_cosine": item.raw_cosine,
                "decision": item.decision,
            }
            for item in top_candidates
        ]
        template = self.prompt_path.read_text(encoding="utf-8")
        prompt = (
            template.replace("{{axis_json}}", json.dumps(axis_payload, ensure_ascii=False))
            .replace("{{candidates_json}}", json.dumps(ranked_payload, ensure_ascii=False))
            .replace("{{max_candidates}}", str(self.max_candidates))
        )
        if "{{" in prompt or "}}" in prompt:
            raise ValueError("hypothesis refiner prompt contains an unresolved placeholder")
        if len(prompt) > 4_096:
            raise ValueError("hypothesis refiner prompt exceeds the 4096-character limit")
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
            "--log-disable",
            "--no-perf",
            "--output-file",
            str(output_path),
            "--threads",
            str(self.threads),
            "--ctx-size",
            "2048",
            "--predict",
            "384",
            "--temp",
            "0",
            "--top-k",
            "1",
            "--seed",
            "7",
        ]

    @staticmethod
    def _parse_candidates(
        output: str, axis: HypothesisAxis, limit: int
    ) -> tuple[HypothesisCandidate, ...]:
        text = output.strip()
        assistant = list(re.finditer(r"(?:^|\n)Assistant:\s*", text, re.IGNORECASE))
        if assistant:
            text = text[assistant[-1].end() :].strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError("Qwen hypothesis output is not valid JSON") from error
        if not isinstance(payload, dict) or set(payload) != {"candidates"}:
            raise ValueError("Qwen hypothesis output must contain only a candidates array")
        raw_candidates = payload["candidates"]
        if not isinstance(raw_candidates, list) or len(raw_candidates) > limit:
            raise ValueError(f"Qwen may return at most {limit} candidates")

        existing = {item.text_en.casefold().strip() for item in axis.candidates}
        seen: set[str] = set()
        candidates: list[HypothesisCandidate] = []
        for raw in raw_candidates:
            if not isinstance(raw, dict) or set(raw) != {"text_en", "text_ru"}:
                continue
            english = raw["text_en"].strip() if isinstance(raw["text_en"], str) else ""
            russian = raw["text_ru"].strip() if isinstance(raw["text_ru"], str) else ""
            normalized = english.casefold()
            if (
                not 8 <= len(english) <= 180
                or not 4 <= len(russian) <= 180
                or not re.search(r"[A-Za-z]", english)
                or not re.search(r"[А-Яа-яЁё]", russian)
                or normalized in existing
                or normalized in seen
            ):
                continue
            seen.add(normalized)
            index = len(candidates) + 1
            candidates.append(
                HypothesisCandidate(
                    candidate_id=f"iterative_{index}",
                    text_en=english,
                    text_ru=russian,
                    polarity="positive",
                    opposes=(),
                )
            )
        return tuple(candidates)

    def propose(
        self, axis: HypothesisAxis, top_candidates: tuple[RankedCandidate, ...]
    ) -> ProposalResult:
        """Run one deterministic, timeout-bounded proposal call."""
        prompt = self._build_prompt(axis, top_candidates)
        started = time.perf_counter()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as output_file:
            output_path = Path(output_file.name)
        try:
            subprocess.run(
                self._command(prompt, output_path),
                check=True,
                capture_output=True,
                timeout=self.timeout_seconds,
            )
            output = output_path.read_text(encoding="utf-8")
            candidates = self._parse_candidates(output, axis, self.max_candidates)
        finally:
            output_path.unlink(missing_ok=True)
        return ProposalResult(candidates, round((time.perf_counter() - started) * 1000, 3))
