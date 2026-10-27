from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from shsd.analyze import (
    _active_levels,
    _AudioWindowBuilder,
    _coalesce_capture_updates,
    _mark_initial_capture_gap,
    _mark_prefetch_drop_coverage,
    _match_window,
    _music_detail_allowed,
    _narration_batches,
    _SelectedVideoWork,
    _timed_audio_work,
    _timed_video_work,
    _video_signal_frame,
    _VideoWorkSelector,
)
from shsd.embeddings.provider import DEFAULT_IMAGE_SOFT_TOKENS, EmbeddingRecord
from shsd.ingest.decoder import (
    CaptureSpan,
    DecodedFrame,
    _CaptureSpanBoundaryTracker,
)
from shsd.memory import (
    EventStore,
    TemporalEventReducer,
    TimelineClaim,
    TimelineEvent,
    WatermarkTracker,
)
from shsd.sampling import AdaptiveSamplingController, EmbeddingNovelty
from shsd.semantic import HypothesisAxis, HypothesisCandidate, MatchPolicy, SemanticMatcher
from shsd.workers.scheduler import (
    AdmissionDecision,
    LoadMode,
    RuntimeLoadController,
    WorkPriority,
)

ROOT = Path(__file__).parents[2]


def test_audio_window_builder_discards_resampler_tail_below_minimum() -> None:
    short_tail = _AudioWindowBuilder(window_ms=5_000)
    short_tail.window_start_ms = 90_000
    short_tail.parts = [np.zeros(3_999, dtype=np.float32)]
    short_tail.buffered = 3_999
    assert short_tail.finish() == []

    minimum_tail = _AudioWindowBuilder(window_ms=5_000)
    minimum_tail.window_start_ms = 90_000
    minimum_tail.parts = [np.zeros(4_000, dtype=np.float32)]
    minimum_tail.buffered = 4_000
    windows = minimum_tail.finish()
    assert len(windows) == 1
    assert windows[0][0:2] == (90_000, 90_250)
    assert windows[0][2].size == 4_000


def _accepted_event(event_id: str, start_ms: int) -> TimelineEvent:
    claim = TimelineClaim(
        claim_id="claim-music-present",
        label="music_present",
        text_ru="Слышна музыка.",
        decision="accepted",
        raw_cosine=0.8,
        margin=0.2,
        evidence_refs=(f"audio:{start_ms}-{start_ms + 1000}",),
        window_ids=(f"window-{event_id}",),
        model_revision="embedding-test",
        sample_count=2,
    )
    return TimelineEvent(
        stream_id="stream-test",
        epoch=0,
        event_id=event_id,
        revision=3,
        start_ms=start_ms,
        end_ms=start_ms + 1000,
        kind="music_started",
        level="L2",
        state="refined",
        modality_mask={"audio": True, "video": False, "speech": False},
        claims=(claim,),
        supersedes_revision=2,
    )


def test_narration_batches_put_confirmed_music_details_before_scene_claims() -> None:
    scene_claim = TimelineClaim(
        claim_id="scene",
        label="conversation_dominant",
        text_ru="На первом плане слышен разговор людей.",
        decision="accepted",
        raw_cosine=0.8,
        margin=0.2,
        evidence_refs=("audio:1000-6000",),
        window_ids=("window-scene",),
        model_revision="embedding-test",
        sample_count=2,
        premise_state="music_confirmed",
        premise_claim_id="music-premise",
        premise_evidence_refs=("axis:music_presence",),
    )
    percussion_claim = TimelineClaim(
        claim_id="percussion",
        label="percussion_present",
        text_ru="В музыке отчётливо слышен ритм ударных.",
        decision="accepted",
        raw_cosine=0.8,
        margin=0.2,
        evidence_refs=("axis:percussion_presence",),
        window_ids=("window-detail",),
        model_revision="embedding-test",
        sample_count=2,
        premise_state="music_confirmed",
        premise_claim_id="music-premise",
        premise_evidence_refs=("axis:music_presence",),
    )
    event = TimelineEvent(
        stream_id="stream-test",
        epoch=0,
        event_id="event-test",
        revision=1,
        start_ms=1_000,
        end_ms=6_000,
        kind="audio_scene_changed",
        level="L2",
        state="refined",
        modality_mask={"audio": True, "video": False, "speech": False},
        claims=(scene_claim, percussion_claim),
    )

    batches = _narration_batches([event], stream_id="stream-test", epoch=0)

    assert [claim.claim_id.rsplit(":", 1)[-1] for claim in batches[0].claims] == [
        "percussion",
        "scene",
    ]


def test_timed_audio_work_is_monotonic_when_window_arrives_after_capture_spans() -> None:
    items = [
        CaptureSpan("audio", 0, 20, "done"),
        CaptureSpan("audio", 20, 40, "done"),
        (0, 5_000, np.zeros(8, dtype=np.float32)),
        CaptureSpan("audio", 5_000, 5_020, "done"),
    ]

    work = list(_timed_audio_work(items))

    assert [item[0] for item in work] == [20, 40, 5_000, 5_020]


def test_timed_video_work_does_not_move_back_before_its_capture_packet() -> None:
    frame0 = DecodedFrame(type("Frame", (), {"pts": 0, "time_base": None})())
    frame1 = DecodedFrame(type("Frame", (), {"pts": 33, "time_base": None})())
    items = [
        CaptureSpan("video", 0, 33, "done"),
        _SelectedVideoWork(frame0.frame, 0, True, True),
        CaptureSpan("video", 33, 66, "done"),
        _SelectedVideoWork(frame1.frame, 33, True, False),
    ]

    work = list(_timed_video_work(items))

    assert [item[0] for item in work] == [33, 33, 66, 66]


def test_capture_updates_coalesce_without_filling_gaps_or_drops() -> None:
    spans = [
        CaptureSpan("video", 0, 100, "done"),
        CaptureSpan("audio", 0, 20, "done"),
        CaptureSpan("video", 100, 200, "done"),
        CaptureSpan("video", 250, 300, "dropped", "ring_overflow"),
    ]
    frame = DecodedFrame(type("Frame", (), {"pts": 0, "time_base": None})())
    source = [(span.modality, span) for span in spans] + [("video", frame)]
    observed: list[CaptureSpan] = []
    work = list(_coalesce_capture_updates(source, on_pending=observed.append))
    captures = [item for _, item in work if isinstance(item, CaptureSpan)]
    assert captures == [
        CaptureSpan("video", 0, 200, "done"),
        CaptureSpan("video", 250, 300, "dropped", "ring_overflow"),
        CaptureSpan("audio", 0, 20, "done"),
    ]
    assert ("video", frame) in work
    assert observed == []


def test_capture_coalescer_reports_pending_coverage_on_close() -> None:
    span = CaptureSpan("video", 0, 33, "done")
    frame = DecodedFrame(type("Frame", (), {"pts": 0, "time_base": None})())
    observed: list[CaptureSpan] = []
    work = _coalesce_capture_updates(
        [("video", span), ("video", frame)], on_pending=observed.append
    )
    assert next(work) == ("video", frame)
    work.close()
    assert observed == [span]


def test_prefetch_drops_create_audio_and_speech_coverage_gaps() -> None:
    tracker = WatermarkTracker("audio-drop", required_modalities={"audio", "speech"})

    _mark_prefetch_drop_coverage(
        tracker,
        "audio",
        (0, 1_000, np.zeros(8, dtype=np.float32)),
        "prefetch_queue_full",
        speech_available=True,
    )

    snapshot = tracker.snapshot(through_ms=1_000)
    assert snapshot.modality_cursors["audio"]["E"] == 1_000
    assert snapshot.modality_cursors["speech"]["C"] == 1_000
    assert snapshot.modality_cursors["speech"]["E"] == 1_000
    assert sum(issue.status == "dropped" for issue in snapshot.issues) == 3


def test_initial_live_capture_offsets_are_reported_as_gaps_without_stalling_c() -> None:
    tracker = WatermarkTracker("live-offset", required_modalities={"audio", "video"})

    _mark_initial_capture_gap(tracker, "audio", 394)
    _mark_initial_capture_gap(tracker, "video", 184)
    tracker.mark("C", 394, 1_394, "done", modality="audio")
    tracker.mark("C", 184, 1_184, "done", modality="video")

    snapshot = tracker.snapshot(through_ms=1_394)
    assert snapshot.C_ms == 1_184
    assert [
        (issue.modality, issue.start_ms, issue.end_ms, issue.reason)
        for issue in snapshot.issues
        if issue.stage == "C" and issue.status == "gap"
    ] == [
        ("audio", 0, 394, "not_observed_by_decoder"),
        ("video", 0, 184, "not_observed_by_decoder"),
    ]


def test_capture_tracker_infers_missing_packet_durations_from_next_pts() -> None:
    tracker = _CaptureSpanBoundaryTracker()

    assert tracker.push("video", 0, 1, "done", None, duration_known=False) == ()
    inferred = tracker.push("video", 209, 210, "done", None, duration_known=False)

    assert [(span.start_ms, span.end_ms) for span in inferred] == [(0, 209)]
    assert [(span.start_ms, span.end_ms) for span in tracker.finish()] == [(209, 210)]


def test_prefetch_drops_only_mark_selected_video_embeddings() -> None:
    tracker = WatermarkTracker("video-drop", required_modalities={"video"})
    frame = _SelectedVideoWork(object(), 1_000, True, False)

    _mark_prefetch_drop_coverage(tracker, "video", frame, "prefetch_queue_full")
    assert tracker.spans("E", modality="video") == ()

    embedding_frame = _SelectedVideoWork(object(), 5_000, False, True)
    _mark_prefetch_drop_coverage(tracker, "video", embedding_frame, "prefetch_queue_full")

    spans = tracker.spans("E", modality="video")
    assert [(span.start_ms, span.end_ms, span.status) for span in spans] == [
        (5_000, 5_001, "dropped")
    ]


def test_dropped_video_embedding_releases_stride_for_retry() -> None:
    load_controller = RuntimeLoadController()
    for index in range(5):
        load_controller.register_source(f"source-{index}")
    sampling = AdaptiveSamplingController(profile="standard", window_ms=5_000)
    selector = _VideoWorkSelector(
        window_ms=5_000,
        source_duration_ms=None,
        sampling=sampling,
        load_controller=load_controller,
    )

    first_frame = DecodedFrame(
        type("Frame", (), {"pts": 20_000, "time_base": Fraction(1, 1_000)})()
    )
    selected = selector.push(first_frame)[0]
    assert isinstance(selected, _SelectedVideoWork)
    assert selected.embedding_selected
    assert selected.on_embedding_drop is not None

    tracker = WatermarkTracker("video-retry", required_modalities={"video"})
    _mark_prefetch_drop_coverage(tracker, "video", selected, "prefetch_queue_full")
    retry_frame = DecodedFrame(
        type("Frame", (), {"pts": 20_100, "time_base": Fraction(1, 1_000)})()
    )
    retried = selector.push(retry_frame)[0]

    assert isinstance(retried, _SelectedVideoWork)
    assert retried.embedding_selected
    assert [
        (span.start_ms, span.end_ms, span.status) for span in tracker.spans("E", modality="video")
    ] == [(20_000, 20_001, "dropped")]


def test_adaptive_video_reuses_the_low_resolution_frame_for_l0() -> None:
    low_resolution = np.zeros((90, 160, 3), dtype=np.uint8)

    class Frame:
        pts = 0
        time_base = Fraction(1, 1_000)

        def __init__(self) -> None:
            self.conversions = 0

        def reformat(self, *, width: int, height: int, format: str) -> Frame:
            assert (width, height, format) == (160, 90, "rgb24")
            return self

        def to_ndarray(self) -> np.ndarray:
            self.conversions += 1
            return low_resolution

    frame = Frame()
    selector = _VideoWorkSelector(
        window_ms=5_000,
        source_duration_ms=None,
        sampling=AdaptiveSamplingController(profile="adaptive", window_ms=5_000),
    )

    selected = selector.push(DecodedFrame(frame))[0]

    assert isinstance(selected, _SelectedVideoWork)
    assert selected.signal_frame_small is low_resolution
    assert _video_signal_frame(selected) is low_resolution
    assert frame.conversions == 1


def test_higher_requested_levels_activate_semantic_prerequisites() -> None:
    assert _active_levels(frozenset({"L3"})) == frozenset({"L1", "L2", "L3"})
    assert _active_levels(frozenset({"L2"})) == frozenset({"L1", "L2"})


def test_l1_commit_watermark_advances_for_each_completed_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shsd import analyze as analyze_module

    fixture = ROOT / "tests" / "fixtures" / "media" / "av_sync_20s.mp4"
    model = {"revision": "914f7f89142e33e77833254d9c9b90c3cef7303b"}

    class FakeProvider:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.serial = 0

        def _record(
            self, modality: str, interval: tuple[int, int] | None = None
        ) -> EmbeddingRecord:
            self.serial += 1
            vector = np.zeros(768, dtype=np.float32)
            vector[0] = 1.0
            return EmbeddingRecord(
                embedding=vector,
                model_revision=model["revision"],
                input_preprocess_version="fake-v1",
                modality=modality,
                embedding_dim=768,
                norm=1.0,
                created_at="2026-10-26T00:00:00+00:00",
                latency_ms=0.1,
                window_id=f"{modality}-{self.serial}",
                interval_ms=interval,
                cache_hit=False,
            )

        def encode_texts(self, texts: list[str], *, cache_namespace: str = ""):
            del cache_namespace
            return [self._record("text") for _ in texts]

        def encode_audio(
            self, _samples: np.ndarray, *, interval_ms: tuple[int, int]
        ) -> EmbeddingRecord:
            return self._record("audio", interval_ms)

        def encode_frame(
            self,
            _frame: np.ndarray,
            pts_ms: int,
            *,
            max_soft_tokens: int = DEFAULT_IMAGE_SOFT_TOKENS,
        ) -> EmbeddingRecord:
            del max_soft_tokens
            return self._record("image", (pts_ms, pts_ms + 1))

    monkeypatch.setattr(analyze_module, "EmbeddingProvider", FakeProvider)
    rows: list[dict[str, Any]] = []
    metrics = analyze_module.analyze_media(
        fixture,
        model,
        ROOT / "models",
        stream_id="progressive-l1",
        threads=1,
        window_ms=5_000,
        policy=MatchPolicy(0.6, 0.05),
        levels=frozenset({"L0", "L1"}),
        event_database=tmp_path / "progressive-l1.sqlite3",
        emit=rows.append,
    )

    committed = [
        int(row["watermarks"]["R"]["L1"])
        for row in rows
        if row.get("record_type") == "watermark"
        and isinstance(row.get("watermarks"), dict)
        and int(row["watermarks"].get("R", {}).get("L1", 0)) > 0
    ]
    assert len(set(committed)) >= 2
    assert committed == sorted(committed)
    final = metrics["final_watermarks"]
    assert final["R"]["L1"] == final["C"]


def test_speech_opt_in_emits_revisions_without_changing_audio_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shsd import analyze as analyze_module

    fixture = ROOT / "tests" / "fixtures" / "media" / "audio_speech_ru.wav"
    model = {"revision": "914f7f89142e33e77833254d9c9b90c3cef7303b"}

    class FakeProvider:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        @staticmethod
        def record(modality: str, index: int = 0, interval: tuple[int, int] | None = None):
            vector = np.zeros(768, dtype=np.float32)
            vector[0] = 1.0
            return EmbeddingRecord(
                embedding=vector,
                model_revision=model["revision"],
                input_preprocess_version="fake-v1",
                modality=modality,
                embedding_dim=768,
                norm=1.0,
                created_at="2026-10-26T00:00:00+00:00",
                latency_ms=0.1,
                window_id=f"{modality}-{index}-{interval}",
                interval_ms=interval,
                cache_hit=False,
            )

        def encode_texts(self, candidates: list[str], *, cache_namespace: str = ""):
            del cache_namespace
            return [self.record("text", index) for index, _ in enumerate(candidates)]

        def encode_audio(self, _samples: np.ndarray, *, interval_ms: tuple[int, int]):
            return self.record("audio", interval=interval_ms)

    monkeypatch.setattr(analyze_module, "EmbeddingProvider", FakeProvider)
    monkeypatch.setattr(
        analyze_module,
        "GigaAMTranscriber",
        lambda *_args, **_kwargs: lambda _samples: "Проверка отдельной ASR дорожки.",
    )

    def run(
        name: str,
        enabled: bool,
        controller: RuntimeLoadController | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        metrics = analyze_module.analyze_media(
            fixture,
            model,
            ROOT / "models",
            stream_id=f"stream-{name}",
            threads=1,
            window_ms=5_000,
            policy=MatchPolicy(0.6, 0.05),
            levels=frozenset({"L0", "L1"}),
            event_database=tmp_path / f"{name}.sqlite3",
            emit=rows.append,
            speech_enabled=enabled,
            runtime_load_controller=controller,
            load_source_id=f"source-{name}",
        )
        return rows, metrics

    baseline_rows, baseline_metrics = run("baseline", False)
    speech_rows, speech_metrics = run("speech", True)
    pressure_controller = RuntimeLoadController()
    original_admit = pressure_controller.admit

    def deny_asr(priority: WorkPriority) -> AdmissionDecision:
        if priority == WorkPriority.L2_ASR:
            return AdmissionDecision(False, priority, LoadMode.CRITICAL, "load_critical")
        return original_admit(priority)

    monkeypatch.setattr(pressure_controller, "admit", deny_asr)
    pressure_rows, pressure_metrics = run("speech-pressure", True, pressure_controller)
    audio_failure_rows: list[dict[str, Any]] = []
    failure_metrics: dict[str, Any]

    def failed_transcriber(*_args: Any, **_kwargs: Any):
        def transcribe(_samples: np.ndarray) -> str:
            raise RuntimeError("ASR fixture failure")

        return transcribe

    monkeypatch.setattr(analyze_module, "GigaAMTranscriber", failed_transcriber)
    audio_failure_rows, failure_metrics = run("speech-failure", True)
    audio_baseline = [
        row
        for row in baseline_rows
        if row.get("record_type") == "observation" and row.get("modality") == "audio"
    ]
    audio_speech = [
        row
        for row in speech_rows
        if row.get("record_type") == "observation" and row.get("modality") == "audio"
    ]
    segments = [row for row in speech_rows if row.get("record_type") == "speech_segment"]
    pressure_segments = [row for row in pressure_rows if row.get("record_type") == "speech_segment"]
    baseline_matches = [row for row in baseline_rows if row.get("record_type") == "window_match"]
    speech_matches = [row for row in speech_rows if row.get("record_type") == "window_match"]
    failure_matches = [
        row for row in audio_failure_rows if row.get("record_type") == "window_match"
    ]

    def signature(rows: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
        return [
            (
                row["start_ms"],
                row["end_ms"],
                row["axis_id"],
                row["candidate_id"],
                row["decision"],
            )
            for row in rows
        ]

    assert audio_speech == audio_baseline
    assert signature(baseline_matches) == signature(speech_matches)
    assert signature(baseline_matches) == signature(failure_matches)
    assert baseline_metrics["window_match_count"] == speech_metrics["window_match_count"]
    assert speech_metrics["speech_worker"]["submitted"] == 1
    assert speech_metrics["speech_worker"]["outstanding"] == 0
    assert speech_metrics["speech_worker"]["admission_dropped"] == 0
    assert [segment["status"] for segment in segments] == ["partial", "final"]
    assert segments[0]["text"] == "Проверка отдельной ASR дорожки."
    assert segments[0]["start_ms"] == segments[1]["start_ms"]
    assert segments[0]["end_ms"] == segments[1]["end_ms"]
    assert speech_metrics["speech_segment_count"] == 1
    assert speech_metrics["speech_error_count"] == 0
    assert pressure_metrics["speech_worker"]["submitted"] == 1
    assert pressure_metrics["speech_worker"]["admission_dropped"] == 0
    assert [segment["status"] for segment in pressure_segments] == ["partial", "final"]
    audio_failed = [
        row
        for row in audio_failure_rows
        if row.get("record_type") == "observation" and row.get("modality") == "audio"
    ]
    failed_segments = [
        row for row in audio_failure_rows if row.get("record_type") == "speech_segment"
    ]
    assert audio_failed == audio_baseline
    assert failure_metrics["speech_error_count"] == 1
    assert failed_segments[0]["status"] == "failed"
    assert "ASR fixture failure" in failed_segments[0]["error"]


def test_narration_batches_keep_exact_revisions_and_unique_source_claim_ids() -> None:
    batches = _narration_batches(
        [_accepted_event("event-b", 1000), _accepted_event("event-a", 0)],
        stream_id="stream-test",
        epoch=0,
    )

    assert len(batches) == 1
    request = batches[0]
    assert [(item.event_id, item.revision) for item in request.event_refs] == [
        ("event-a", 3),
        ("event-b", 3),
    ]
    assert len({item.claim_id for item in request.claims}) == 2
    assert {item.claim_id for item in request.claims} == {
        "event-a:claim-music-present",
        "event-b:claim-music-present",
    }
    accepted_sources = request.facts_payload()["accepted_claims"]
    assert len(accepted_sources) == 1
    assert set(accepted_sources[0]["source_claim_ids"]) == {
        "event-a:claim-music-present",
        "event-b:claim-music-present",
    }


@pytest.mark.parametrize(
    ("candidate_id", "decision", "expected"),
    [
        ("music_present", "accepted", True),
        ("music_and_speech", "accepted", True),
        ("music_present", "uncertain", True),
        ("conversation_dominant", "accepted", False),
        ("unknown", "uncertain", False),
    ],
)
def test_music_detail_axes_route_from_accepted_music_scene(
    candidate_id: str, decision: str, expected: bool
) -> None:
    assert _music_detail_allowed(candidate_id, decision) is expected


def test_window_match_emits_multiple_persistently_supported_instrument_events() -> None:
    axis = HypothesisAxis(
        axis_id="instrument_family",
        modality="audio",
        mutually_exclusive=False,
        candidates=(
            HypothesisCandidate("synth", "Synth timbre.", "Синтезаторный тембр.", "positive", ()),
            HypothesisCandidate("strings", "String timbre.", "Струнный тембр.", "positive", ()),
            HypothesisCandidate("brass", "Brass timbre.", "Медный тембр.", "positive", ()),
        ),
    )
    vectors = {
        "synth": np.eye(1, 768, 0, dtype=np.float32).reshape(-1),
        "strings": np.array([0.8, 0.6] + [0.0] * 766, dtype=np.float32),
        "brass": np.eye(1, 768, 2, dtype=np.float32).reshape(-1),
    }
    matcher = SemanticMatcher()
    reducer = TemporalEventReducer(min_repeats=2, max_gap_ms=500)
    emitted: list[dict[str, object]] = []
    accepted_claim_windows: list[str] = []

    with EventStore(":memory:") as store:
        store.begin_epoch("stream-test", 0)
        for index, start_ms in enumerate((0, 1_000)):
            record = EmbeddingRecord(
                embedding=np.eye(1, 768, 0, dtype=np.float32).reshape(-1),
                model_revision="test-model",
                input_preprocess_version="test-v1",
                modality="audio",
                embedding_dim=768,
                norm=1.0,
                created_at="2026-10-26T00:00:00+00:00",
                latency_ms=0.1,
                window_id=f"audio-window-{index}",
                interval_ms=(start_ms, start_ms + 1_000),
                cache_hit=False,
            )
            counts = _match_window(
                source=Path("synthetic.mp4"),
                stream_id="stream-test",
                epoch=0,
                start_ms=start_ms,
                end_ms=start_ms + 1_000,
                modality="audio",
                record=record,
                axes=[(axis, vectors)],
                policy=MatchPolicy(0.6, 0.05, top_k=1),
                matcher=matcher,
                reducer=reducer,
                store=store,
                emit=emitted.append,
                sampling_novelty_score=0.8 if index else None,
                signal_delta_score=0.4 if index else None,
                embedding_novelty=(
                    EmbeddingNovelty(
                        comparable=True,
                        cosine_similarity=0.7,
                        novelty_score=0.3,
                        reference_window_id="audio-window-0",
                    )
                    if index
                    else None
                ),
                on_accepted_claim=lambda window_id=record.window_id: accepted_claim_windows.append(
                    window_id
                ),
            )
            assert counts == (1, 0 if index == 0 else 2, 0)

        matches = [item for item in emitted if item["record_type"] == "window_match"]
        events = [item for item in emitted if item["record_type"] == "event"]

    assert len(matches) == 2
    assert len(matches[0]["supported_candidates"]) == 2  # type: ignore[arg-type]
    novelty = matches[1]["sampling_novelty"]
    assert isinstance(novelty, dict)
    assert novelty["score"] == pytest.approx(0.8)
    assert novelty["signal_delta_score"] == pytest.approx(0.4)
    assert novelty["embedding_novelty_score"] == pytest.approx(0.3)
    assert novelty["similarity_is_probability"] is False
    assert accepted_claim_windows
    assert {item["claims"][0]["label"] for item in events} == {"synth", "strings"}  # type: ignore[index]
