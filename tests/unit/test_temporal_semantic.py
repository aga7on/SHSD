from __future__ import annotations

import numpy as np

from shsd.memory.models import TimelineClaim, TimelineEvent
from shsd.semantic.hypotheses import HypothesisAxis, HypothesisCandidate
from shsd.semantic.matcher import MatchPolicy, SemanticMatcher
from shsd.semantic.temporal import BoundedAudioEmbeddingHistory, TemporalAudioRefiner

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
            ),
        ),
        {"music_present": _unit(0), "music_absent": _unit(1)},
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
