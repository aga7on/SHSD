from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from shsd.captions.narrator import (
    NarrationASRQuote,
    NarrationClaim,
    NarrationEventRef,
    NarrationRequest,
    QwenNarrator,
)


def _request() -> NarrationRequest:
    return NarrationRequest(
        stream_id="stream-1",
        epoch=0,
        event_refs=(NarrationEventRef("event-1", 2),),
        claims=(
            NarrationClaim(
                claim_id="claim-1",
                event_id="event-1",
                revision=2,
                start_ms=1000,
                end_ms=3000,
                text_ru="Слышна музыка.",
                evidence_refs=("audio:1000-3000",),
            ),
        ),
        asr_quotes=(
            NarrationASRQuote(
                segment_id="asr-1",
                start_ms=1500,
                end_ms=2200,
                text="Привет.",
                quality=0.85,
                source="gigaam-v3",
            ),
        ),
        state={"active_music": "music_present"},
        delta={"changed_fields": ["active_music"]},
    )


def _narrator(tmp_path: Path, *, max_input_chars: int = 16_384) -> QwenNarrator:
    prompt_path = tmp_path / "prompt.jinja"
    prompt_path.write_text("Только факты: {{facts_json}}", encoding="utf-8")
    narrator = QwenNarrator.__new__(QwenNarrator)
    narrator.model = {"revision": "qwen-test"}
    narrator.model_revision = "qwen-test"
    narrator.model_path = tmp_path / "qwen.gguf"
    narrator.llama_cli = tmp_path / "llama-cli.exe"
    narrator.prompt_path = prompt_path
    narrator.schema_path = tmp_path / "schema.json"
    narrator.template_path = tmp_path / "chat.jinja"
    narrator.threads = 2
    narrator.max_tokens = 48
    narrator.timeout_seconds = 3.0
    narrator.max_input_chars = max_input_chars
    return narrator


def test_request_rejects_unaccepted_or_unreferenced_claims() -> None:
    with pytest.raises(ValueError, match="only accepted"):
        NarrationClaim(
            "claim-x", "event-1", 1, 0, 1000, "Может быть музыка.", "uncertain"  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="supplied event revision"):
        NarrationRequest(
            "stream-1",
            0,
            (NarrationEventRef("event-1", 1),),
            (
                NarrationClaim(
                    "claim-1",
                    "event-1",
                    2,
                    0,
                    1000,
                    "Слышна музыка.",
                    evidence_refs=("a",),
                ),
            ),
        )


def test_prompt_contains_only_accepted_sources_and_temporal_context(tmp_path: Path) -> None:
    prompt = _narrator(tmp_path)._build_prompt(_request())
    payload = json.loads(prompt.split("Только факты: ", maxsplit=1)[1])
    assert len(payload["accepted_claims"]) == 1
    assert payload["accepted_claims"][0]["decision"] == "accepted"
    assert payload["event_revisions"] == [{"event_id": "event-1", "revision": 2}]
    assert payload["asr_quotes"][0]["quality"] == 0.85
    assert payload["state"] == {"active_music": "music_present"}
    assert payload["delta"] == {"changed_fields": ["active_music"]}
    assert payload["time_range"] == {"start_ms": 1000, "end_ms": 3000}


def test_extractor_discards_llama_conversation_prompt() -> None:
    output = "User:\nскрытая инструкция\nAssistant:\nСлышна музыка."
    assert QwenNarrator._extract_caption(output) == "Слышна музыка."


def test_command_pins_nonthinking_template_cpu_limits_and_output_contract(tmp_path: Path) -> None:
    narrator = _narrator(tmp_path)
    output_path = tmp_path / "generated.txt"
    command = narrator._command(narrator._build_prompt(_request()), output_path)
    assert command[0] == str(narrator.llama_cli)
    assert command[command.index("--output-file") + 1] == str(output_path)
    assert command[command.index("--chat-template-file") + 1] == str(narrator.template_path)
    assert command[command.index("--threads") + 1] == "2"
    assert command[command.index("--predict") + 1] == "48"
    assert "--single-turn" in command
    assert "--jinja" in command


def test_generated_caption_uses_known_sources_and_matching_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    narrator = _narrator(tmp_path)
    request = _request()
    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        command = args[0]
        output_path = Path(command[command.index("--output-file") + 1])  # type: ignore[union-attr]
        output_path.write_text("Слышна музыка. Привет.", encoding="utf-8")
        assert kwargs["timeout"] == 3.0
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", run)
    result = narrator.narrate(request)
    assert result.status == "generated"
    assert result.response.used_claim_ids == ("asr-1", "claim-1")
    assert result.response.start_ms == 1000
    assert result.response.end_ms == 3000
    payload = result.to_dict()
    assert payload["prompt_version"] == "narrator-ru-v1"
    assert set(payload) == {
        "schema_version",
        "record_type",
        "caption_ru",
        "used_claim_ids",
        "new_unsupported_claims",
        "time_range",
        "warnings",
        "status",
        "backend",
        "model_revision",
        "prompt_version",
        "event_revisions",
        "latency_ms",
        "generated_token_count",
        "generation_ms",
        "tokens_per_second",
    }
    assert payload["event_revisions"] == [{"event_id": "event-1", "revision": 2}]
    assert payload["new_unsupported_claims"] == []


@pytest.mark.parametrize("bad_output", ["", "No music is audible.", "<think>reasoning</think>"])
def test_invalid_output_uses_source_only_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_output: str
) -> None:
    narrator = _narrator(tmp_path)
    request = _request()

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        command = args[0]
        output_path = Path(command[command.index("--output-file") + 1])  # type: ignore[union-attr]
        output_path.write_text(bad_output, encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", run)
    result = narrator.narrate(request)
    assert result.status == "fallback"
    assert result.response.caption_ru == "Слышна музыка. Цитата: «Привет.»"
    assert result.response.warnings == ("qwen_output_invalid",)


def test_timeout_falls_back_and_large_request_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    narrator = _narrator(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired(args[0], 3)),
    )
    result = narrator.narrate(_request())
    assert result.status == "fallback"
    assert result.response.warnings == ("qwen_timeout",)
    with pytest.raises(ValueError, match="chunk is"):
        _narrator(tmp_path, max_input_chars=256)._build_prompt(_request())


def test_unsupported_instrument_claim_is_replaced_with_source_only_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    narrator = _narrator(tmp_path)
    request = _request()

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        command = args[0]
        output_path = Path(command[command.index("--output-file") + 1])  # type: ignore[union-attr]
        output_path.write_text("Слышна музыка. Гитара.", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", run)
    result = narrator.narrate(request)
    assert result.status == "fallback"
    assert result.response.caption_ru == "Слышна музыка. Цитата: «Привет.»"
    assert "гитара" not in result.response.caption_ru.casefold()
    assert result.response.warnings == ("unsupported_terms",)


def test_contradictory_negation_is_replaced_with_source_only_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    narrator = _narrator(tmp_path)
    request = _request()

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        command = args[0]
        output_path = Path(command[command.index("--output-file") + 1])  # type: ignore[union-attr]
        output_path.write_text("Музыка не слышна.", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", run)
    result = narrator.narrate(request)
    assert result.status == "fallback"
    assert "Музыка не слышна" not in result.response.caption_ru
    assert result.response.warnings == ("unsupported_terms",)
