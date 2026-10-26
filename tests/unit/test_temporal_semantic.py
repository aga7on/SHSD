from __future__ import annotations

from dataclasses import replace

import numpy as np

from shsd.detectors.types import SignalObservation
from shsd.memory.models import TimelineClaim, TimelineEvent
from shsd.semantic.hypotheses import HypothesisAxis, HypothesisCandidate
from shsd.semantic.matcher import MatchPolicy, SemanticMatcher
from shsd.semantic.temporal import (
    BoundedAudioEmbeddingHistory,
    TemporalAudioRefiner,
    _music_scene_supports_details,
)

MODEL_REVISION = "temporal-test-model"


def _unit(index: int, *, sign: float = 1.0) -> np.ndarray:
    vector = np.zeros(768, dtype=np.float32)
    vector[index] = sign
    return vector


def _axis() -> tuple[HypothesisAxis, dict[str, np.ndarray]]:
    return (
        HypothesisAxis(
            axis_id="music_presence",
            modality="audio",
            mutually_exclusive=True,
            candidates=(
                HypothesisCandidate(
                    candidate_id="music_present",
                    text_en="Music is audible.",
                    text_ru="Слышна музыка.",
                    polarity="positive",
                    opposes=("music_absent",),
                ),
                HypothesisCandidate(
                    candidate_id="music_absent",
                    text_en="No music is audible.",
                    text_ru="Музыка не слышна.",
                    polarity="negative",
                    opposes=("music_present",),
                ),
                HypothesisCandidate(
                    candidate_id="music_and_speech",
                    text_en="Music and speech are prominent.",
                    text_ru="Заметны музыка и речь.",
                    polarity="positive",
                    opposes=(),
                ),
            ),
        ),
        {
            "music_present": _unit(0),
            "music_absent": _unit(1),
            "music_and_speech": _unit(2),
        },
    )


def _event(candidate_id: str = "music_present") -> TimelineEvent:
    return TimelineEvent(
        stream_id="temporal-test",
        epoch=0,
        event_id="event-1",
        revision=1,
        start_ms=1_000,
        end_ms=3_000,
        kind="music_started",
        level="L1",
        state="committed",
        modality_mask={"audio": True, "video": False, "speech": False},
        claims=(
            TimelineClaim(
                claim_id=f"claim-music_presence-{candidate_id}",
                label=candidate_id,
                text_ru="Слышна музыка.",
                decision="accepted",
                raw_cosine=0.9,
                margin=0.2,
                evidence_refs=(
                    "audio:1000-2000",
                    "embedding:window-1",
                    "embedding:window-2",
                    "axis:music_presence",
                ),
                window_ids=("window-1", "window-2"),
                model_revision=MODEL_REVISION,
                sample_count=2,
            ),
        ),
    )


def _refiner(vectors: list[tuple[str, int, int, np.ndarray]]) -> TemporalAudioRefiner:
    history = BoundedAudioEmbeddingHistory(capacity=8)
    for window_id, start_ms, end_ms, embedding in vectors:
        history.add(
            start_ms=start_ms,
            end_ms=end_ms,
            window_id=window_id,
            model_revision=MODEL_REVISION,
            embedding=embedding,
        )
    axis, candidate_vectors = _axis()
    return TemporalAudioRefiner(
        history=history,
        axes=[(axis, candidate_vectors)],
        matcher=SemanticMatcher(),
        policy=MatchPolicy(minimum_similarity=0.6, minimum_margin=0.05),
        context_padding_ms=1_000,
    )


def test_l2_confirms_candidate_with_aggregate_and_neighbor_audio() -> None:
    refiner = _refiner(
        [
            ("before", 0, 1_000, _unit(1)),
            ("window-1", 1_000, 2_000, _unit(0)),
            ("window-2", 2_000, 3_000, _unit(0)),
            ("after", 3_000, 4_000, _unit(0)),
        ]
    )

    refined, report = refiner.refine(_event())

    assert report["status"] == "confirmed"
    assert refined.claims[0].decision == "accepted"
    assert refined.claims[0].premise_state == "music_confirmed"
    assert refined.claims[0].sample_count == 2
    assert "l2:temporal-audio:1000-3000" in refined.claims[0].evidence_refs
    claim_report = report["claims"][0]
    assert claim_report["aggregate"]["decision"] == "accepted"
    assert claim_report["temporal_context"]["before_candidate_id"] == "music_absent"
    assert claim_report["temporal_context"]["after_candidate_id"] == "music_present"
    assert claim_report["thresholds"]["minimum_margin"] == 0.05


def test_l2_downgrades_event_when_adjacent_windows_disagree() -> None:
    mixed_audio = _unit(0) * 0.1 + _unit(1) * 0.9
    refiner = _refiner(
        [
            ("before", 0, 1_000, _unit(1)),
            ("window-1", 1_000, 2_000, _unit(0)),
            ("window-2", 2_000, 3_000, mixed_audio),
            ("after", 3_000, 4_000, _unit(1)),
        ]
    )

    refined, report = refiner.refine(_event())

    assert report["status"] == "abstained"
    assert report["claims"][0]["support"]["target_votes"] == 1
    assert refined.kind == "unknown"
    assert refined.claims[0].decision == "uncertain"


def test_audio_embedding_history_is_bounded_and_source_ordered() -> None:
    history = BoundedAudioEmbeddingHistory(capacity=2)
    for index in range(3):
        history.add(
            start_ms=index * 1_000,
            end_ms=(index + 1) * 1_000,
            window_id=f"w{index}",
            model_revision=MODEL_REVISION,
            embedding=_unit(index),
        )

    context = history.context(
        start_ms=1_000,
        end_ms=3_000,
        model_revision=MODEL_REVISION,
        padding_ms=0,
    )

    assert len(history) == 2
    assert [item.window_id for item in context] == ["w1", "w2"]


def test_l2_adds_new_music_details_with_signal_and_neighbor_evidence() -> None:
    history = BoundedAudioEmbeddingHistory(capacity=8)
    change = SignalObservation(
        2_000, 3_000, "onset_count_delta", 0.9, "audio-window-delta-v1", 2.0, "count"
    )
    for window_id, start_ms in (
        ("before", 0),
        ("window-1", 1_000),
        ("window-2", 2_000),
        ("after", 3_000),
    ):
        history.add(
            start_ms=start_ms,
            end_ms=start_ms + 1_000,
            window_id=window_id,
            model_revision=MODEL_REVISION,
            embedding=_unit(0),
            signal_summary={"onset_count": 5, "mean_spectral_centroid_hz": 1_200},
            signal_deltas=(change,) if window_id == "window-2" else (),
        )
    scene_axis, scene_vectors = _axis()
    vocal_axis = HypothesisAxis(
        axis_id="vocal_presence",
        modality="audio",
        mutually_exclusive=True,
        level="L2",
        candidates=(
            HypothesisCandidate("solo_vocals", "Solo vocals.", "Сольный вокал.", "positive", ()),
            HypothesisCandidate(
                "choral_vocals", "Choral vocals.", "Хоровой вокал.", "positive", ()
            ),
        ),
    )
    vocal_vectors = {"solo_vocals": _unit(0), "choral_vocals": _unit(1)}
    refiner = TemporalAudioRefiner(
        history=history,
        axes=[(scene_axis, scene_vectors)],
        detail_axes=[(vocal_axis, vocal_vectors)],
        matcher=SemanticMatcher(),
        policy=MatchPolicy(minimum_similarity=0.6, minimum_margin=0.05),
        context_padding_ms=1_000,
    )

    source_event = _event()
    source_claim = replace(
        source_event.claims[0],
        label="conversation_dominant",
        decision="accepted",
        text_ru="На первом плане слышен разговор людей.",
        candidate_hypotheses=(
            ("conversation_dominant", 0.75, "accepted"),
            ("music_and_speech", 0.68, "uncertain"),
        ),
    )
    refined, report = refiner.refine(replace(source_event, claims=(source_claim,)))

    assert [claim.label for claim in refined.claims] == ["conversation_dominant"]
    assert refined.claims[0].premise_state == "music_possible"
    assert report["strategy"] == "coarse_to_fine_temporal_audio_v2"
    assert report["music_premise"]["state"] == "music_possible"
    assert report["music_premise"]["publication_allowed"] is False
    assert report["detail_status"] == "exploratory_only"
    assert report["new_details"] == []
    assert report["static_details"][0]["candidate_id"] == "solo_vocals"
    assert report["static_details"][0]["per_window_accepted_count"] == 2
    assert report["static_details"][0]["publication_status"] == (
        "suppressed_music_premise_not_confirmed"
    )
    assert report["coarse_candidates"][1]["candidate_id"] == "music_and_speech"
    assert report["signal_context"]
    assert report["acoustic_changes"][0]["subtype"] == "onset_count_delta"
    assert report["static_details"][0]["axis_id"] == "vocal_presence"
    assert {item["relation"] for item in report["neighbor_hypotheses"]} == {
        "before_event",
        "after_event",
    }


def test_l2_reports_uncertain_detail_scores_without_promoting_them() -> None:
    history = BoundedAudioEmbeddingHistory(capacity=8)
    mixed = _unit(0) + _unit(1)
    for window_id, start_ms in (
        ("before", 0),
        ("window-1", 1_000),
        ("window-2", 2_000),
        ("after", 3_000),
    ):
        history.add(
            start_ms=start_ms,
            end_ms=start_ms + 1_000,
            window_id=window_id,
            model_revision=MODEL_REVISION,
            embedding=mixed,
        )
    scene_axis, scene_vectors = _axis()
    vocal_axis = HypothesisAxis(
        axis_id="vocal_presence",
        modality="audio",
        mutually_exclusive=True,
        level="L2",
        candidates=(
            HypothesisCandidate(
                "vocals_present", "Singing vocals.", "Слышен вокал.", "positive", ()
            ),
            HypothesisCandidate(
                "vocals_absent", "No singing vocals.", "Вокала не слышно.", "negative", ()
            ),
        ),
    )
    refiner = TemporalAudioRefiner(
        history=history,
        axes=[(scene_axis, scene_vectors)],
        detail_axes=[
            (vocal_axis, {"vocals_present": _unit(0), "vocals_absent": _unit(1)})
        ],
        matcher=SemanticMatcher(),
        policy=MatchPolicy(minimum_similarity=0.6, minimum_margin=0.05),
        context_padding_ms=1_000,
    )

    refined, report = refiner.refine(_event())

    assert not [claim for claim in refined.claims if claim.claim_id.startswith("claim-l2-")]
    assert report["new_details"] == []
    detail = report["static_details"][0]
    assert detail["axis_id"] == "vocal_presence"
    assert detail["candidate_id"] == "vocals_present"
    assert detail["aggregate_supported"] is False
    assert detail["per_window_accepted_count"] == 0
    assert detail["window_scores"][0]["decision"] == "uncertain"


def test_music_scene_detail_routing_accepts_mixed_music_and_speech() -> None:
    assert _music_scene_supports_details("music_present", "accepted", 0.8)
    assert _music_scene_supports_details("music_and_speech", "accepted", 0.8)
    assert _music_scene_supports_details("music_present", "uncertain", 0.8)
    assert _music_scene_supports_details(
        "conversation_dominant",
        "accepted",
        0.8,
        (("conversation_dominant", 0.8, "accepted"), ("music_and_speech", 0.68, "uncertain")),
    )
    assert not _music_scene_supports_details(
        "conversation_dominant",
        "accepted",
        0.8,
        (("conversation_dominant", 0.8, "accepted"),),
    )
    assert not _music_scene_supports_details(
        "conversation_dominant",
        "accepted",
        0.8,
        (("conversation_dominant", 0.8, "accepted"), ("music_and_speech", 0.68, "rejected")),
    )


def test_l2_publishes_music_detail_with_confirmed_music_and_speech_premise() -> None:
    history = BoundedAudioEmbeddingHistory(capacity=8)
    for window_id, start_ms in (
        ("before", 0),
        ("window-1", 1_000),
        ("window-2", 2_000),
        ("after", 3_000),
    ):
        history.add(
            start_ms=start_ms,
            end_ms=start_ms + 1_000,
            window_id=window_id,
            model_revision=MODEL_REVISION,
            embedding=_unit(2),
        )
    scene_axis, scene_vectors = _axis()
    vocal_axis = HypothesisAxis(
        axis_id="vocal_presence",
        modality="audio",
        mutually_exclusive=True,
        level="L2",
        candidates=(
            HypothesisCandidate("solo_vocals", "Solo vocals.", "Сольный вокал.", "positive", ()),
            HypothesisCandidate(
                "choral_vocals", "Choral vocals.", "Хоровой вокал.", "positive", ()
            ),
        ),
    )
    refiner = TemporalAudioRefiner(
        history=history,
        axes=[(scene_axis, scene_vectors)],
        detail_axes=[(vocal_axis, {"solo_vocals": _unit(2), "choral_vocals": _unit(3)})],
        matcher=SemanticMatcher(),
        policy=MatchPolicy(minimum_similarity=0.6, minimum_margin=0.05),
        context_padding_ms=1_000,
    )
    source_event = _event("music_and_speech")
    source_claim = replace(
        source_event.claims[0],
        text_ru="Заметны музыка и речь.",
        raw_cosine=0.95,
        margin=0.9,
    )

    refined, report = refiner.refine(replace(source_event, claims=(source_claim,)))

    detail = next(claim for claim in refined.claims if claim.label == "solo_vocals")
    assert report["music_premise"]["state"] == "music_confirmed"
    assert report["music_premise"]["publication_allowed"] is True
    assert detail.decision == "accepted"
    assert detail.premise_state == "music_confirmed"
    assert detail.premise_claim_id == source_claim.claim_id
    assert "axis:music_presence" in detail.premise_evidence_refs
    assert "axis:vocal_presence" in detail.evidence_refs


def test_l2_publishes_music_detail_with_confirmed_music_only_premise() -> None:
    history = BoundedAudioEmbeddingHistory(capacity=8)
    for window_id, start_ms in (
        ("before", 0),
        ("window-1", 1_000),
        ("window-2", 2_000),
        ("after", 3_000),
    ):
        history.add(
            start_ms=start_ms,
            end_ms=start_ms + 1_000,
            window_id=window_id,
            model_revision=MODEL_REVISION,
            embedding=_unit(0),
        )
    scene_axis, scene_vectors = _axis()
    detail_axis = HypothesisAxis(
        axis_id="percussion_presence",
        modality="audio",
        mutually_exclusive=True,
        level="L2",
        candidates=(
            HypothesisCandidate(
                "percussion_present", "Drums are audible.", "Слышны ударные.", "positive", ()
            ),
            HypothesisCandidate(
                "percussion_absent",
                "No drums are audible.",
                "Ударных не слышно.",
                "negative",
                (),
            ),
        ),
    )
    refiner = TemporalAudioRefiner(
        history=history,
        axes=[(scene_axis, scene_vectors)],
        detail_axes=[
            (detail_axis, {"percussion_present": _unit(0), "percussion_absent": _unit(3)})
        ],
        matcher=SemanticMatcher(),
        policy=MatchPolicy(minimum_similarity=0.6, minimum_margin=0.05),
        context_padding_ms=1_000,
    )

    refined, report = refiner.refine(_event("music_present"))

    detail = next(claim for claim in refined.claims if claim.label == "percussion_present")
    assert report["music_premise"]["state"] == "music_confirmed"
    assert detail.decision == "accepted"
    assert detail.premise_state == "music_confirmed"
    assert detail.premise_claim_id == "claim-music_presence-music_present"


def test_conversation_only_with_no_music_candidate_does_not_probe_music_details() -> None:
    refiner = _refiner(
        [
            ("before", 0, 1_000, _unit(1)),
            ("window-1", 1_000, 2_000, _unit(1)),
            ("window-2", 2_000, 3_000, _unit(1)),
            ("after", 3_000, 4_000, _unit(1)),
        ]
    )
    source_claim = replace(
        _event().claims[0],
        label="conversation_dominant",
        decision="accepted",
        text_ru="На первом плане слышен разговор.",
        candidate_hypotheses=(("conversation_dominant", 0.82, "accepted"),),
    )

    refined, report = refiner.refine(replace(_event(), claims=(source_claim,)))

    assert len(refined.claims) == 1
    assert refined.claims[0].premise_state == "not_supported"
    assert report["music_premise"]["state"] == "not_supported"
    assert report["static_details"] == []
    assert report["new_details"] == []


def test_uncertain_music_premise_allows_internal_l2_search_but_no_claim_publication() -> None:
    mixed = _unit(0) + _unit(1)
    mixed = mixed / np.linalg.norm(mixed)
    history = BoundedAudioEmbeddingHistory(capacity=8)
    for window_id, start_ms in (
        ("before", 0),
        ("window-1", 1_000),
        ("window-2", 2_000),
        ("after", 3_000),
    ):
        history.add(
            start_ms=start_ms,
            end_ms=start_ms + 1_000,
            window_id=window_id,
            model_revision=MODEL_REVISION,
            embedding=mixed,
        )
    scene_axis, scene_vectors = _axis()
    vocal_axis = HypothesisAxis(
        axis_id="vocal_presence",
        modality="audio",
        mutually_exclusive=True,
        level="L2",
        candidates=(
            HypothesisCandidate("solo_vocals", "Solo vocals.", "Сольный вокал.", "positive", ()),
            HypothesisCandidate(
                "choral_vocals", "Choral vocals.", "Хоровой вокал.", "positive", ()
            ),
        ),
    )
    refiner = TemporalAudioRefiner(
        history=history,
        axes=[(scene_axis, scene_vectors)],
        detail_axes=[(vocal_axis, {"solo_vocals": mixed, "choral_vocals": _unit(3)})],
        matcher=SemanticMatcher(),
        policy=MatchPolicy(minimum_similarity=0.6, minimum_margin=0.05),
        context_padding_ms=1_000,
    )
    source_claim = replace(
        _event().claims[0],
        decision="uncertain",
        raw_cosine=float(1 / np.sqrt(2)),
        margin=0.0,
    )

    refined, report = refiner.refine(replace(_event(), claims=(source_claim,)))

    assert report["music_premise"]["state"] == "music_possible"
    assert report["detail_status"] == "exploratory_only"
    assert report["static_details"][0]["per_window_accepted_count"] == 2
    assert report["new_details"] == []
    assert not any(claim.label == "solo_vocals" for claim in refined.claims)
