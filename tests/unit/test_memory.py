from __future__ import annotations

from dataclasses import replace

import pytest

from shsd.detectors.types import SignalObservation
from shsd.memory import (
    EventStore,
    StaleRevisionError,
    TemporalEventReducer,
    TemporalStateReducer,
    TimelineClaim,
    TimelineEvent,
    WatermarkTracker,
    WindowMatch,
)

REVISION = "model-revision-a"


def _match(
    window_id: str,
    start_ms: int,
    end_ms: int,
    candidate_id: str = "music_present",
) -> WindowMatch:
    text = {
        "music_present": "В аудио слышна музыка.",
        "music_absent": "В аудио не слышно музыки.",
        "unknown": None,
    }[candidate_id]
    return WindowMatch(
        stream_id="stream-1",
        epoch=0,
        start_ms=start_ms,
        end_ms=end_ms,
        axis_id="music_presence",
        candidate_id=candidate_id,
        text_ru=text,
        decision="uncertain" if candidate_id == "unknown" else "accepted",
        raw_cosine=0.82,
        margin=0.21,
        modality="audio",
        evidence_refs=(f"audio:{start_ms}-{end_ms}",),
        window_id=window_id,
        model_revision=REVISION,
    )


def _event(revision: int = 1) -> TimelineEvent:
    return TimelineEvent(
        stream_id="stream-1",
        epoch=0,
        event_id="event-1",
        revision=revision,
        start_ms=0,
        end_ms=1000 * revision,
        kind="music_started",
        level="L1",
        state="draft",
        modality_mask={"audio": True, "video": False, "speech": False},
        claims=(
            TimelineClaim(
                claim_id="claim-music_presence-music_present",
                label="music_present",
                text_ru="В аудио слышна музыка.",
                decision="accepted",
                raw_cosine=0.82,
                margin=0.21,
                evidence_refs=("audio:0-1000",),
                window_ids=("w1",),
                model_revision=REVISION,
                sample_count=1,
            ),
        ),
        supersedes_revision=revision - 1 if revision > 1 else None,
    )


def test_timeline_claim_premise_provenance_round_trips_and_legacy_json_defaults() -> None:
    claim = replace(
        _event().claims[0],
        premise_state="music_confirmed",
        premise_claim_id="claim-music-scene",
        premise_evidence_refs=("audio:0-1000", "axis:music_presence"),
    )

    assert TimelineClaim.from_dict(claim.to_dict()) == claim
    legacy = claim.to_dict()
    legacy.pop("premise_state")
    legacy.pop("premise_claim_id")
    legacy.pop("premise_evidence_refs")
    legacy_claim = TimelineClaim.from_dict(legacy)
    assert legacy_claim.premise_state is None
    assert legacy_claim.premise_claim_id is None
    assert legacy_claim.premise_evidence_refs == ()


def test_human_verified_action_claim_retains_annotation_and_entity_action_object() -> None:
    claim = TimelineClaim(
        claim_id="review:action-1",
        label="human_verified_visual_action",
        text_ru="Мужчина встаёт с кровати.",
        decision="accepted",
        raw_cosine=None,
        margin=None,
        evidence_refs=("visual-frame:video-1:0:1000", "visual-frame:video-1:0:2000"),
        window_ids=("human-review:video_01",),
        model_revision="human-review-record",
        sample_count=2,
        annotation_verification="human_verified",
        annotator_id="reviewer-1",
        guide_version="f10-blind-review-v1",
        visual_subject_ru="мужчина",
        visual_action_ru="встаёт",
        visual_object_ru="кровать",
    )

    restored = TimelineClaim.from_dict(claim.to_dict())

    assert restored == claim
    assert restored.raw_cosine is None
    assert restored.annotation_verification == "human_verified"
    assert restored.visual_subject_ru == "мужчина"


def test_unannotated_claim_keeps_legacy_serialization_shape() -> None:
    value = _event().claims[0].to_dict()

    assert "annotation_verification" not in value
    assert "annotator_id" not in value
    assert "visual_subject_ru" not in value
    assert "music_layer_type" not in value


def test_human_verified_claim_requires_complete_provenance_and_eao_fields() -> None:
    with pytest.raises(ValueError, match="verification, annotator, and guide"):
        TimelineClaim(
            claim_id="review:action-1",
            label="human_verified_visual_action",
            text_ru="Мужчина встаёт с кровати.",
            decision="accepted",
            raw_cosine=None,
            margin=None,
            evidence_refs=("visual-frame:video-1:0:1000",),
            window_ids=("human-review:video_01",),
            model_revision="human-review-record",
            sample_count=1,
            annotation_verification="human_verified",
            annotator_id="reviewer-1",
        )


def test_watermark_revisioned_mark_atomically_changes_status() -> None:
    tracker = WatermarkTracker("revisioned", required_modalities={"audio"})
    tracker.mark("D", 0, 1_000, "done", level="L1")

    tracker.mark_revisioned("D", 0, 1_000, "skipped", level="L1", reason="runtime_backpressure")
    tracker.mark_revisioned("D", 0, 1_000, "done", level="L1")

    spans = tracker.spans("D", level="L1")
    assert [(span.status, span.revision, span.reason) for span in spans] == [("done", 3, None)]


def _state_event(
    event_id: str,
    kind: str,
    start_ms: int,
    end_ms: int,
    label: str,
    *,
    samples: int = 2,
    decision: str = "accepted",
    level: str = "L1",
) -> TimelineEvent:
    return TimelineEvent(
        stream_id="state-stream",
        epoch=0,
        event_id=event_id,
        revision=1,
        start_ms=start_ms,
        end_ms=end_ms,
        kind=kind,
        level=level,
        state="draft",
        modality_mask={"audio": True, "video": False, "speech": False},
        claims=(
            TimelineClaim(
                claim_id=f"claim-{event_id}",
                label=label,
                text_ru=None,
                decision=decision,
                raw_cosine=0.82,
                margin=0.21,
                evidence_refs=(f"event:{event_id}",),
                window_ids=tuple(f"{event_id}-window-{i}" for i in range(samples)),
                model_revision=REVISION,
                sample_count=samples,
            ),
        ),
    )


def test_temporal_reducer_requires_persistence_and_extends_stable_event() -> None:
    reducer = TemporalEventReducer(min_repeats=2, max_gap_ms=500)

    assert reducer.ingest(_match("w1", 0, 1000)) is None
    first = reducer.ingest(_match("w2", 800, 1800))
    assert first is not None
    assert (first.start_ms, first.end_ms, first.revision) == (0, 1800, 1)
    assert first.kind == "music_started"
    assert first.claims[0].window_ids == ("w1", "w2")
    assert set(first.claims[0].evidence_refs) == {"audio:0-1000", "audio:800-1800"}

    extended = reducer.ingest(_match("w3", 1600, 2600))
    assert extended is not None
    assert extended.event_id == first.event_id
    assert extended.revision == 2
    assert extended.supersedes_revision == 1
    assert extended.end_ms == 2600
    assert extended.claims[0].sample_count == 3
    assert reducer.ingest(_match("w3", 1600, 2600)) is None


def test_temporal_reducer_tracks_simultaneous_independent_instrument_claims() -> None:
    reducer = TemporalEventReducer(min_repeats=2, max_gap_ms=500)
    events: list[TimelineEvent] = []
    for index, start_ms in enumerate((0, 800), start=1):
        end_ms = start_ms + 1_000
        for candidate_id, text in (
            ("synth", "Синтезаторный тембр."),
            ("strings", "Струнный тембр."),
        ):
            event = reducer.ingest(
                WindowMatch(
                    stream_id="stream-1",
                    epoch=0,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    axis_id="instrument_family",
                    candidate_id=candidate_id,
                    text_ru=text,
                    decision="accepted",
                    raw_cosine=0.9,
                    margin=0.2,
                    modality="audio",
                    evidence_refs=(f"audio:{start_ms}-{end_ms}",),
                    window_id=f"w{index}",
                    model_revision=REVISION,
                    candidate_independent=True,
                )
            )
            if event is not None:
                events.append(event)

    assert len(events) == 2
    assert {event.claims[0].label for event in events} == {"synth", "strings"}
    assert {event.kind for event in events} == {"instrument_detected"}
    assert all(event.claims[0].sample_count == 2 for event in events)


def test_candidate_change_creates_a_new_event_after_hysteresis() -> None:
    reducer = TemporalEventReducer(min_repeats=2, max_gap_ms=500)
    reducer.ingest(_match("w1", 0, 1000))
    first = reducer.ingest(_match("w2", 800, 1800))
    assert first is not None

    assert reducer.ingest(_match("w3", 1600, 2600, "music_absent")) is None
    stopped = reducer.ingest(_match("w4", 2400, 3400, "music_absent"))
    assert stopped is not None
    assert stopped.event_id != first.event_id
    assert stopped.kind == "music_stopped"
    assert stopped.start_ms == 1600


def test_uncertain_music_match_emits_unknown_and_does_not_upgrade_it_in_place() -> None:
    reducer = TemporalEventReducer(min_repeats=2, max_gap_ms=500)
    uncertain = replace(_match("w1", 0, 1000), decision="uncertain")
    assert reducer.ingest(uncertain) is None
    unknown = reducer.ingest(replace(uncertain, window_id="w2", start_ms=800, end_ms=1800))

    assert unknown is not None
    assert unknown.kind == "unknown"
    assert unknown.claims[0].decision == "uncertain"
    assert unknown.claims[0].label == "music_present"

    assert reducer.ingest(_match("w3", 1600, 2600)) is None
    accepted = reducer.ingest(_match("w4", 2400, 3400))
    assert accepted is not None
    assert accepted.kind == "music_started"
    assert accepted.event_id != unknown.event_id


def test_positive_scene_cut_signal_becomes_deduplicated_l0_event() -> None:
    reducer = TemporalEventReducer()
    observation = SignalObservation(
        start_ms=1000,
        end_ms=2000,
        subtype="scene_cut",
        quality=0.9,
        method_version="video-frame-diff-v1",
        value=True,
        unit="boolean",
    )

    event = reducer.ingest_signal("stream-1", 0, observation, window_id="cut-1")

    assert event is not None
    assert event.kind == "scene_changed"
    assert event.level == "L0"
    assert event.state == "committed"
    assert event.modality_mask == {"audio": False, "video": True, "speech": False}
    assert "method:video-frame-diff-v1" in event.claims[0].evidence_refs
    assert reducer.ingest_signal("stream-1", 0, observation, window_id="cut-1") is None


def test_gap_breaks_a_stable_event_and_seek_epoch_is_isolated() -> None:
    reducer = TemporalEventReducer(min_repeats=2, max_gap_ms=500)
    reducer.ingest(_match("w1", 0, 1000))
    first = reducer.ingest(_match("w2", 800, 1800))
    assert first is not None
    assert reducer.ingest(_match("w3", 5000, 6000)) is None
    restarted = reducer.ingest(_match("w4", 5800, 6800))
    assert restarted is not None
    assert restarted.event_id != first.event_id

    new_epoch_match = replace(_match("w1", 0, 1000), epoch=1)
    assert reducer.ingest(new_epoch_match) is None
    epoch_one = reducer.ingest(replace(_match("w2", 800, 1800), epoch=1))
    assert epoch_one is not None
    assert epoch_one.epoch == 1
    assert epoch_one.event_id != first.event_id
    with pytest.raises(ValueError, match="stale match from epoch"):
        reducer.ingest(_match("late-old-epoch", 6800, 7800))


def test_event_store_appends_revisions_and_rejects_stale_compare_and_swap(tmp_path) -> None:
    with EventStore(tmp_path / "timeline.sqlite3") as store:
        first = _event()
        store.append(first, expected_revision=0)
        second = replace(first, revision=2, end_ms=2000, supersedes_revision=1)
        store.append(second, expected_revision=1)

        current = store.current("stream-1", 0, "event-1")
        history = store.history("stream-1", 0, "event-1")
        assert current == second
        assert [event.revision for event in history] == [1, 2]
        with pytest.raises(StaleRevisionError, match="stale event revision"):
            store.append(second, expected_revision=1)


def test_event_store_keeps_epochs_separate() -> None:
    with EventStore(":memory:") as store:
        store.append(_event(), expected_revision=0)
        store.begin_epoch("stream-1", 1)
        with pytest.raises(StaleRevisionError, match="stale event epoch"):
            store.append(_event(), expected_revision=0)
        other_epoch = replace(_event(), epoch=1)
        store.append(other_epoch, expected_revision=0)

        assert store.current("stream-1", 0, "event-1") is not None
        assert store.current("stream-1", 1, "event-1") == other_epoch


def test_event_store_replays_captions_and_stream_metadata_after_reopen(tmp_path) -> None:
    path = tmp_path / "persisted-stream.sqlite3"
    caption = {
        "schema_version": 1,
        "record_type": "caption",
        "caption_ru": "На записи слышен ударный звук.",
        "time_range": {"start_ms": 0, "end_ms": 1_000},
        "used_claim_ids": ["claim-1"],
    }
    metadata = {"source": "clip.wav", "status": "completed", "epoch": 0}
    with EventStore(path) as store:
        assert store.append_caption("stream-1", 0, caption) is True
        assert store.append_caption("stream-1", 0, caption) is False
        store.save_stream_metadata("stream-1", metadata)

    with EventStore(path) as store:
        assert store.captions("stream-1", 0) == (caption,)
        assert store.load_stream_metadata("stream-1") == metadata


def test_event_store_revisions_speech_segments_and_restores_latest(tmp_path) -> None:
    path = tmp_path / "speech.sqlite3"
    partial = {
        "record_type": "speech_segment",
        "segment_id": "segment-1",
        "revision": 1,
        "status": "partial",
        "start_ms": 1_000,
        "end_ms": 2_000,
        "text": "Проверка речи.",
    }
    final = {
        **partial,
        "revision": 2,
        "supersedes_revision": 1,
        "status": "final",
        "source_complete": True,
    }
    with EventStore(path) as store:
        store.append_speech_segment("stream-1", 0, partial)
        with pytest.raises(StaleRevisionError, match="stale speech segment revision"):
            store.append_speech_segment(
                "stream-1", 0, {**final, "revision": 3, "supersedes_revision": 2}
            )
        store.append_speech_segment("stream-1", 0, {**final, "text": "Итоговая расшифровка."})
    with EventStore(path) as store:
        current = store.speech_segments("stream-1", 0)
    assert len(current) == 1
    assert current[0]["status"] == "final"
    assert current[0]["text"] == "Итоговая расшифровка."


def test_temporal_state_tracks_snapshots_and_deduplicates_revisions() -> None:
    reducer = TemporalStateReducer()
    started = _state_event("start-1", "music_started", 0, 1000, "music_present")

    delta = reducer.ingest(started)

    assert delta is not None
    assert delta.previous.active_music is None
    assert delta.current.active_music == "music_present"
    assert delta.current.last_meaningful_change_ms == 0
    assert delta.novelty_score is None
    assert delta.published is True
    assert reducer.ingest(started) is None

    duplicate_window = _state_event("duplicate-window", "music_started", 0, 1000, "music_present")
    duplicate_window = replace(
        duplicate_window,
        claims=(replace(duplicate_window.claims[0], window_ids=started.claims[0].window_ids),),
    )
    assert reducer.ingest(duplicate_window) is None

    extension = replace(started, revision=2, end_ms=1500, supersedes_revision=1)
    assert reducer.ingest(extension) is None
    assert reducer.ingest(extension) is None


def test_temporal_state_holds_overlapping_change_until_a_comparable_boundary() -> None:
    reducer = TemporalStateReducer(min_repeats=2)
    reducer.ingest(_state_event("music-1", "music_started", 0, 1000, "ambient"))

    overlapping = reducer.ingest(_state_event("music-2", "music_changed", 800, 1800, "drums"))

    assert overlapping is not None
    assert overlapping.comparison == "ambiguous"
    assert overlapping.pending is True
    assert overlapping.published is False
    assert overlapping.current.active_music == "ambient"

    confirmed = reducer.ingest(_state_event("music-3", "music_changed", 1800, 2800, "drums"))

    assert confirmed is not None
    assert confirmed.previous.active_music == "ambient"
    assert confirmed.current.active_music == "drums"
    assert confirmed.current.last_meaningful_change_ms == 800
    assert confirmed.novelty_score == 1.0
    assert confirmed.changed_fields == ("active_music",)
    assert confirmed.published is True


def test_temporal_state_rejects_uncertain_claims_and_requires_hysteresis() -> None:
    reducer = TemporalStateReducer(min_repeats=2)
    first = reducer.ingest(
        _state_event("pending-1", "music_started", 0, 1000, "ambient", samples=1)
    )
    assert first is not None and first.pending is True
    assert first.current.active_music is None

    uncertain = reducer.ingest(
        _state_event("uncertain-1", "music_started", 1000, 2000, "ambient", decision="uncertain")
    )
    assert uncertain is not None and uncertain.comparison == "ambiguous"
    assert uncertain.current.active_music is None

    accepted = reducer.ingest(
        _state_event("accepted-1", "music_started", 2000, 3000, "ambient", samples=2)
    )
    assert accepted is not None and accepted.published is True
    assert accepted.current.active_music == "ambient"


def test_temporal_state_order_changes_result_and_tracks_scene_and_speakers() -> None:
    start_then_stop = TemporalStateReducer()
    forward_deltas = [
        start_then_stop.ingest(_state_event("a-start", "music_started", 0, 1000, "ambient")),
        start_then_stop.ingest(_state_event("a-stop", "music_stopped", 1000, 2000, "music_absent")),
    ]

    stop_then_start = TemporalStateReducer()
    reverse_deltas = [
        stop_then_start.ingest(_state_event("b-stop", "music_stopped", 0, 1000, "music_absent")),
        stop_then_start.ingest(_state_event("b-start", "music_started", 1000, 2000, "ambient")),
    ]

    assert start_then_stop.current("state-stream", 0).active_music is None
    assert stop_then_start.current("state-stream", 0).active_music == "ambient"
    assert [item.changed_fields if item is not None else () for item in forward_deltas] != [
        item.changed_fields if item is not None else () for item in reverse_deltas
    ]

    scene = _state_event("scene-1", "visual_scene", 3000, 4000, "interior")
    speakers = _state_event("speech-1", "speech_detected", 3000, 4000, "speech_present")
    stop_then_start.ingest(scene)
    stop_then_start.ingest(speakers)
    snapshot = stop_then_start.current("state-stream", 0)
    assert snapshot.active_scene == "interior"
    assert snapshot.active_speakers == ("speaker_unknown",)
    assert snapshot.active_music == "ambient"

    measured_cut = _state_event(
        "cut-1", "scene_changed", 4000, 5000, "scene_cut", samples=1, level="L0"
    )
    cut_delta = stop_then_start.ingest(measured_cut)
    assert cut_delta is not None and cut_delta.published is True
    assert cut_delta.current.active_scene == "scene_cut@cut-1"


def test_temporal_state_novelty_requires_comparable_intervals_and_resets_on_epoch() -> None:
    reducer = TemporalStateReducer()
    started = _state_event("music-1", "music_started", 0, 1000, "ambient")
    reducer.ingest(started)

    stable = reducer.ingest(_state_event("music-2", "music_started", 1000, 2000, "ambient"))
    assert stable is not None
    assert stable.comparison == "adjacent"
    assert stable.novelty_score == 0.0
    assert stable.current.last_meaningful_change_ms == 0

    late = reducer.ingest(_state_event("late-music", "music_changed", 500, 1500, "drums"))
    assert late is not None
    assert late.comparison == "ambiguous"
    assert late.current.active_music == "ambient"

    next_epoch = replace(_state_event("epoch-one", "music_started", 0, 1000, "ambient"), epoch=1)
    reducer.ingest(next_epoch)
    assert reducer.current("state-stream", 1).active_music == "ambient"
    assert reducer.current("state-stream", 0).active_music is None
    with pytest.raises(ValueError, match="stale event from epoch"):
        reducer.ingest(_state_event("stale-epoch", "music_started", 2000, 3000, "ambient"))
