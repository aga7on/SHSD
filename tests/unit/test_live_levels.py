from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from shsd.memory.models import TimelineClaim, TimelineEvent
from shsd.memory.store import EventStore
from shsd.workers.live_levels import LiveLevelWorkers
from shsd.workers.scheduler import RuntimeLoadController


class _NarratorResult:
    def __init__(self, request: Any) -> None:
        self.response = SimpleNamespace(
            start_ms=0,
            end_ms=1000,
            new_unsupported_claims=(),
        )
        self.latency_ms = 12.0
        self.backend = "qwen"
        self.status = "generated"
        self.generated_token_count = 5
        self.generation_ms = 10.0
        self.request = request

    def to_dict(self) -> dict[str, object]:
        return {"record_type": "caption", "caption_ru": "Музыка звучит."}


class _FakeNarrator:
    def narrate(self, request: Any) -> _NarratorResult:
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
            make_requests=lambda events: [tuple(events)] if events else [],
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
