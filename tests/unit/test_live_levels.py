from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from shsd.analyze import _narration_batches
from shsd.memory.models import TimelineClaim, TimelineEvent
from shsd.memory.store import EventStore
from shsd.workers.live_levels import LiveLevelWorkers
from shsd.workers.scheduler import RuntimeLoadController


class _NarratorResult:
    def __init__(self, request: Any) -> None:
        self.response = SimpleNamespace(
            caption_ru="\u0421\u043b\u044b\u0448\u043d\u0430 \u043c\u0443\u0437\u044b\u043a\u0430.",
            used_claim_ids=tuple(request.source_ids),
            start_ms=request.time_range[0],
            end_ms=request.time_range[1],
            new_unsupported_claims=(),
        )
        self.event_revisions = request.event_refs
        self.model_revision = "test-model"
        self.prompt_version = "test-prompt"
        self.latency_ms = 12.0
        self.backend = "qwen"
        self.status = "generated"
        self.generated_token_count = 5
        self.generation_ms = 10.0
        self.request = request

    def to_dict(self) -> dict[str, object]:
        return {"record_type": "caption", "caption_ru": "Музыка звучит."}


class _FakeNarrator:
    calls = 0

    def narrate(self, request: Any) -> _NarratorResult:
        type(self).calls += 1
        return _NarratorResult(request)


def _source_event() -> TimelineEvent:
    claim = TimelineClaim(
        claim_id="claim-music",
        label="music_present",
        text_ru="В аудио слышна музыка.",
        decision="accepted",
        raw_cosine=0.9,
        margin=0.1,
        evidence_refs=("audio:0-1000",),
        window_ids=("window-1", "window-2"),
        model_revision="test-model",
        sample_count=2,
    )
    return TimelineEvent(
        stream_id="live-test",
        epoch=0,
        event_id="event-1",
        revision=1,
        start_ms=0,
        end_ms=1000,
        kind="music_started",
        level="L1",
        state="committed",
        modality_mask={"audio": True, "video": False, "speech": False},
        claims=(claim,),
    )


def test_live_workers_commit_l2_before_narrating_l3(tmp_path: Path) -> None:
    emitted: list[dict[str, Any]] = []
    coverage: list[tuple[str, str, int, int, str, str | None]] = []
    with EventStore(tmp_path / "events.sqlite") as store:
        store.begin_epoch("live-test", 0)
        source = _source_event()
        store.append(source, expected_revision=0)
        workers = LiveLevelWorkers(
            store=store,
            load_controller=RuntimeLoadController(),
            emit=emitted.append,
            mark_coverage=lambda *item: coverage.append(item),
            make_requests=lambda events: _narration_batches(events, stream_id="live-test", epoch=0),
            narrator_factory=_FakeNarrator,
            l3_enabled=True,
            l2_capacity=2,
            l3_capacity=2,
        )
        assert workers.submit_event(source)
        assert workers.submit_coverage(((0, 1000),), block=True)
        workers.finish()

        current = store.current_events("live-test", 0)
        assert len(current) == 1
        assert current[0].revision == 2
        assert current[0].level == "L2"
        assert current[0].state == "refined"

    event_records = [item for item in emitted if item.get("record_type") == "event"]
    caption_records = [item for item in emitted if item.get("record_type") == "caption"]
    assert len(event_records) == 1
    assert len(caption_records) == 1
    assert any(item[:2] == ("L2", "R") and item[4] == "done" for item in coverage)
    assert any(item[:2] == ("L3", "D") and item[4] == "done" for item in coverage)
    assert any(item[:2] == ("L3", "R") and item[4] == "done" for item in coverage)


def test_live_workers_skip_repeated_neighbor_qwen_request(tmp_path: Path) -> None:
    emitted: list[dict[str, Any]] = []
    source = _source_event()
    adjacent = replace(
        source,
        event_id="event-2",
        start_ms=2_000,
        end_ms=3_000,
        claims=(
            replace(
                source.claims[0],
                claim_id="claim-music-2",
                evidence_refs=("audio:2000-3000",),
            ),
        ),
    )
    _FakeNarrator.calls = 0

    with EventStore(tmp_path / "deduplicated-events.sqlite") as store:
        store.begin_epoch("live-test", 0)
        store.append(source, expected_revision=0)
        store.append(adjacent, expected_revision=0)
        workers = LiveLevelWorkers(
            store=store,
            load_controller=RuntimeLoadController(),
            emit=emitted.append,
            mark_coverage=lambda *_item: None,
            make_requests=lambda events: _narration_batches(events, stream_id="live-test", epoch=0),
            narrator_factory=_FakeNarrator,
            l3_enabled=True,
        )
        assert workers.submit_event(source)
        assert workers.submit_event(adjacent)
        assert workers.submit_coverage(((0, 1_000), (2_000, 3_000)), block=True)
        workers.finish()
        snapshot = workers.snapshot()

    assert _FakeNarrator.calls == 1
    assert sum(item.get("record_type") == "caption" for item in emitted) == 1
    deduplicated = [item for item in emitted if item.get("record_type") == "narration_deduplicated"]
    assert len(deduplicated) == 1
    assert (
        deduplicated[0]["caption_ru"]
        == "\u0421\u043b\u044b\u0448\u043d\u0430 \u043c\u0443\u0437\u044b\u043a\u0430."
    )
    assert snapshot["l3"]["deduplicated"] == 1
    assert snapshot["narration"]["caption_count"] == 1
    assert snapshot["narration"]["deduplicated_count"] == 1


def test_live_workers_apply_and_report_semantic_l2_refinement(tmp_path: Path) -> None:
    emitted: list[dict[str, Any]] = []
    source = _source_event()

    def refine_l2(event: TimelineEvent) -> tuple[TimelineEvent, dict[str, Any]]:
        claim = replace(event.claims[0], decision="uncertain")
        return (
            replace(event, kind="unknown", claims=(claim,)),
            {
                "record_type": "l2_refinement",
                "event_id": event.event_id,
                "status": "abstained",
            },
        )

    with EventStore(tmp_path / "semantic-events.sqlite") as store:
        store.begin_epoch("live-test", 0)
        store.append(source, expected_revision=0)
        workers = LiveLevelWorkers(
            store=store,
            load_controller=RuntimeLoadController(),
            emit=emitted.append,
            mark_coverage=lambda *_item: None,
            make_requests=lambda _events: [],
            narrator_factory=_FakeNarrator,
            l3_enabled=False,
            refine_l2=refine_l2,
        )
        assert workers.submit_event(source)
        assert workers.submit_coverage(((0, 1_000),), block=True)
        workers.finish()
        snapshot = workers.snapshot()

        current = store.current_events("live-test", 0)
        assert len(current) == 1
        assert current[0].revision == 2
        assert current[0].level == "L2"
        assert current[0].kind == "unknown"
        assert current[0].claims[0].decision == "uncertain"

    assert any(item.get("record_type") == "l2_refinement" for item in emitted)
    assert snapshot["l2"]["semantic_refinement"] == {
        "total": 1,
        "confirmed": 0,
        "abstained": 1,
        "skipped": 0,
    }
