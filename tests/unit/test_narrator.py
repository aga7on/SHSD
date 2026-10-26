from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from shsd.captions.narrator import (
    CaptionDeduplicator,
    NarrationASRQuote,
    NarrationClaim,
    NarrationEventRef,
    NarrationRequest,
    NarrationRequestDeduplicator,
    NarrationResponse,
    NarrationResult,
    QwenNarrator,
    _claim_coverage,
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
            "claim-x",
            "event-1",
            1,
            0,
            1000,
            "Может быть музыка.",
            "uncertain",  # type: ignore[arg-type]
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
    assert result.response.input_claim_ids == ("asr-1", "claim-1")
    assert result.response.expressed_claim_ids == ("asr-1", "claim-1")
    assert result.response.omitted_claim_ids == ()
    assert result.response.uncertain_claim_ids == ()
    assert result.response.start_ms == 1000
    assert result.response.end_ms == 3000
    payload = result.to_dict()
    assert payload["prompt_version"] == "narrator-ru-v2"
    assert set(payload) == {
        "schema_version",
        "record_type",
        "caption_ru",
        "used_claim_ids",
        "input_claim_ids",
        "expressed_claim_ids",
        "omitted_claim_ids",
        "uncertain_claim_ids",
        "claim_coverage",
        "claim_coverage_method",
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


def test_generated_caption_marks_only_claims_it_expresses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    narrator = _narrator(tmp_path)
    request = NarrationRequest(
        stream_id="stream-1",
        epoch=0,
        event_refs=(
            NarrationEventRef("event-1", 1),
            NarrationEventRef("event-2", 1),
            NarrationEventRef("event-3", 1),
        ),
        claims=(
            NarrationClaim(
                claim_id="conversation",
                event_id="event-1",
                revision=1,
                start_ms=1_000,
                end_ms=3_000,
                text_ru="На первом плане слышен разговор людей.",
                evidence_refs=("audio:1000-3000",),
            ),
            NarrationClaim(
                claim_id="scene-cut",
                event_id="event-2",
                revision=1,
                start_ms=2_000,
                end_ms=3_000,
                text_ru="Смена кадра совпадает по времени с обнаруженным звуковым началом.",
                evidence_refs=("video:2000-3000",),
            ),
            NarrationClaim(
                claim_id="percussion",
                event_id="event-3",
                revision=1,
                start_ms=1_000,
                end_ms=3_000,
                text_ru="В музыке отчётливо слышен ритм ударных.",
                evidence_refs=("audio:1000-3000", "axis:percussion_presence"),
            ),
        ),
    )

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        command = args[0]
        output_path = Path(command[command.index("--output-file") + 1])  # type: ignore[union-attr]
        output_path.write_text("На первом плане слышен разговор.", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", run)
    result = narrator.narrate(request)

    assert result.status == "generated"
    assert result.response.input_claim_ids == ("conversation", "percussion", "scene-cut")
    assert result.response.used_claim_ids == ("conversation",)
    assert result.response.expressed_claim_ids == ("conversation",)
    assert result.response.omitted_claim_ids == ("percussion", "scene-cut")
    assert result.response.uncertain_claim_ids == ()
    assert result.response.claim_coverage_method == "conservative_token_overlap_v2"


def test_claim_coverage_keeps_low_overlap_as_uncertain() -> None:
    request = _request()
    claim = request.claims[0]
    request = NarrationRequest(
        stream_id=request.stream_id,
        epoch=request.epoch,
        event_refs=request.event_refs,
        claims=(
            NarrationClaim(
                claim_id=claim.claim_id,
                event_id=claim.event_id,
                revision=claim.revision,
                start_ms=claim.start_ms,
                end_ms=claim.end_ms,
                text_ru="Слышна спокойная инструментальная музыка.",
                evidence_refs=claim.evidence_refs,
            ),
        ),
        asr_quotes=request.asr_quotes,
    )
    coverage = _claim_coverage("Музыка.", request)

    assert coverage["expressed_claim_ids"] == ()
    assert coverage["omitted_claim_ids"] == ("asr-1",)
    assert coverage["uncertain_claim_ids"] == ("claim-1",)


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
    assert "\u0433\u0438\u0442\u0430\u0440\u0430" in result.response.new_unsupported_claims


def test_provenance_accepts_safe_russian_inflection_and_sound_equivalent() -> None:
    request = _request()

    assert (
        QwenNarrator._unsupported_provenance_terms(
            "\u0417\u0432\u0443\u0447\u0438\u0442 \u043c\u0443\u0437\u044b\u043a\u0430.", request
        )
        == ()
    )
    assert QwenNarrator._unsupported_provenance_terms(
        (
            "\u0417\u0432\u0443\u0447\u0438\u0442 \u043c\u0443\u0437\u044b\u043a\u0430 "
            "\u0438 \u0441\u043b\u044b\u0448\u043d\u043e \u0433\u0438\u0442\u0430\u0440\u0443."
        ),
        request,
    ) == ("<unsupported_relation>", "\u0433\u0438\u0442\u0430\u0440\u0443")


def test_provenance_rejects_new_relation_made_only_from_supported_words() -> None:
    request = NarrationRequest(
        stream_id="stream-1",
        epoch=0,
        event_refs=(NarrationEventRef("event-1", 1), NarrationEventRef("event-2", 1)),
        claims=(
            NarrationClaim(
                claim_id="person",
                event_id="event-1",
                revision=1,
                start_ms=1_000,
                end_ms=2_000,
                text_ru="Человек виден на изображении.",
                evidence_refs=("image:1000-2000",),
            ),
            NarrationClaim(
                claim_id="music",
                event_id="event-2",
                revision=1,
                start_ms=1_000,
                end_ms=2_000,
                text_ru="Слышна музыка.",
                evidence_refs=("audio:1000-2000",),
            ),
        ),
    )

    assert QwenNarrator._unsupported_provenance_terms("Человек виден с музыкой.", request) == (
        "<unsupported_relation>",
    )


def test_facts_payload_collapses_repeated_adjacent_claims_but_keeps_provenance() -> None:
    first = _request()
    second_claim = NarrationClaim(
        claim_id="claim-2",
        event_id="event-2",
        revision=1,
        start_ms=4_000,
        end_ms=5_000,
        text_ru=first.claims[0].text_ru,
        evidence_refs=("audio:4000-5000",),
    )
    request = NarrationRequest(
        stream_id=first.stream_id,
        epoch=first.epoch,
        event_refs=(*first.event_refs, NarrationEventRef("event-2", 1)),
        claims=(first.claims[0], second_claim),
    )

    accepted = request.facts_payload()["accepted_claims"]
    assert len(accepted) == 1
    assert accepted[0]["source_claim_ids"] == ["claim-1", "claim-2"]
    assert accepted[0]["start_ms"] == 1_000
    assert accepted[0]["end_ms"] == 5_000
    assert accepted[0]["evidence_refs"] == ["audio:1000-3000", "audio:4000-5000"]


def test_duplicate_claims_do_not_multiply_negation_or_fallback_text() -> None:
    text = (
        "\u041f\u0440\u0438\u0447\u0438\u043d\u043d\u0430\u044f \u0441\u0432\u044f\u0437\u044c "
        "\u043d\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430."
    )
    request = NarrationRequest(
        stream_id="stream-1",
        epoch=0,
        event_refs=(NarrationEventRef("event-1", 1), NarrationEventRef("event-2", 1)),
        claims=(
            NarrationClaim("claim-1", "event-1", 1, 1_000, 3_000, text, evidence_refs=("a",)),
            NarrationClaim("claim-2", "event-2", 1, 4_000, 5_000, text, evidence_refs=("b",)),
        ),
    )

    assert QwenNarrator._unsupported_provenance_terms(text, request) == ()
    assert QwenNarrator._fallback(request, "test").caption_ru == text


def test_provenance_rejects_removed_negation_when_caption_reuses_the_fact() -> None:
    request = NarrationRequest(
        stream_id="stream-1",
        epoch=0,
        event_refs=(NarrationEventRef("event-1", 1),),
        claims=(
            NarrationClaim(
                "claim-1",
                "event-1",
                1,
                1_000,
                2_000,
                (
                    "\u041c\u0443\u0437\u044b\u043a\u0438 \u043d\u0435 "
                    "\u0441\u043b\u044b\u0448\u043d\u043e."
                ),
                evidence_refs=("audio:1000-2000",),
            ),
        ),
    )

    assert QwenNarrator._unsupported_provenance_terms(
        "\u041c\u0443\u0437\u044b\u043a\u0430 \u0441\u043b\u044b\u0448\u043d\u0430.", request
    ) == ("<negation_mismatch>",)


def test_request_deduplicator_skips_identical_neighbor_and_keeps_later_occurrence() -> None:
    deduplicator = NarrationRequestDeduplicator()
    caption_text = "\u0421\u043b\u044b\u0448\u043d\u0430 \u043c\u0443\u0437\u044b\u043a\u0430."

    def request(event_id: str, claim_id: str, start_ms: int, end_ms: int) -> NarrationRequest:
        return NarrationRequest(
            stream_id="stream-1",
            epoch=0,
            event_refs=(NarrationEventRef(event_id, 1),),
            claims=(
                NarrationClaim(
                    claim_id,
                    event_id,
                    1,
                    start_ms,
                    end_ms,
                    caption_text,
                    evidence_refs=(f"audio:{start_ms}-{end_ms}",),
                ),
            ),
        )

    first = request("event-1", "claim-1", 1_000, 3_000)
    adjacent = request("event-2", "claim-2", 4_000, 6_000)
    later = request("event-3", "claim-3", 15_000, 17_000)

    assert deduplicator.should_skip(first) is None
    deduplicator.remember(
        first,
        caption_ru="\u0421\u043b\u044b\u0448\u043d\u0430 \u043c\u0443\u0437\u044b\u043a\u0430.",
    )
    duplicate = deduplicator.should_skip(adjacent)
    assert duplicate is not None
    assert (
        duplicate["caption_ru"]
        == "\u0421\u043b\u044b\u0448\u043d\u0430 \u043c\u0443\u0437\u044b\u043a\u0430."
    )
    assert duplicate["covered_claim_ids"] == ["claim-1", "claim-2"]
    assert [item["event_id"] for item in duplicate["covered_event_revisions"]] == [
        "event-1",
        "event-2",
    ]
    assert deduplicator.should_skip(later) is None


def test_caption_deduplicator_merges_adjacent_revisions_only() -> None:
    deduplicator = CaptionDeduplicator()
    caption_text = "\u0417\u0432\u0443\u0447\u0438\u0442 \u043c\u0443\u0437\u044b\u043a\u0430."

    def result(event_id: str, start_ms: int, end_ms: int, claim_id: str) -> NarrationResult:
        return NarrationResult(
            response=NarrationResponse(
                caption_ru=caption_text,
                used_claim_ids=(claim_id,),
                start_ms=start_ms,
                end_ms=end_ms,
            ),
            status="generated",
            model_revision="qwen-test",
            prompt_version="narrator-ru-v2",
            event_revisions=(NarrationEventRef(event_id, 1),),
            latency_ms=1.0,
        )

    assert (
        deduplicator.process(result("event-1", 1_000, 3_000, "claim-1"))["record_type"] == "caption"
    )
    duplicate = deduplicator.process(result("event-2", 4_000, 6_000, "claim-2"))
    assert duplicate["record_type"] == "caption_deduplicated"
    assert duplicate["deduplication"]["covered_used_claim_ids"] == ["claim-1", "claim-2"]
    assert (
        deduplicator.process(result("event-3", 15_000, 17_000, "claim-3"))["record_type"]
        == "caption"
    )


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
