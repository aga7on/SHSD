from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread

from shsd.ingest.clock import MediaClock
from shsd.ingest.replay import ReplayController
from shsd.memory import EventStore, StaleRevisionError, TimelineClaim, TimelineEvent

MEDIA = Path(__file__).parents[1] / "fixtures" / "media"


def test_pause_resume_preserves_pending_packet_position() -> None:
    controller = ReplayController(
        str(MEDIA / "video_static_3s.mp4"), MediaClock("replay-pause"), mode="fast"
    )
    packets = []
    paused = Event()
    controller.pause()

    def collect_until_second_packet() -> None:
        for packet in controller.packets():
            packets.append(packet)
            if len(packets) == 1:
                controller.pause()
                paused.set()
            elif len(packets) == 2:
                controller.stop()

    worker = Thread(target=collect_until_second_packet, daemon=True)
    worker.start()
    controller.resume()
    assert paused.wait(2)
    time.sleep(0.03)
    assert len(packets) == 1
    controller.resume()
    worker.join(2)

    assert not worker.is_alive()
    assert [packet.packet_index for packet in packets] == [0, 1]
    assert [packet.epoch for packet in packets] == [0, 0]


def test_seek_starts_new_epoch_and_drops_old_cursor_packets() -> None:
    clock = MediaClock("replay-seek")
    epoch_changes = []
    controller = ReplayController(
        str(MEDIA / "av_sync_20s.mp4"),
        clock,
        mode="fast",
        on_epoch_started=lambda stream_id, epoch: epoch_changes.append((stream_id, epoch)),
    )
    packets = controller.packets()

    first = next(packets)
    controller.seek(10_000)
    after_seek = next(packets)

    assert first.epoch == 0
    assert after_seek.epoch == 1
    assert clock.epoch == 1
    assert after_seek.start_ms > first.start_ms
    assert epoch_changes == [("replay-seek", 0), ("replay-seek", 1)]
    controller.stop()
    packets.close()


def test_seek_callback_blocks_a_late_old_epoch_event_write() -> None:
    clock = MediaClock("replay-store")
    with EventStore(":memory:") as store:
        controller = ReplayController(
            str(MEDIA / "av_sync_20s.mp4"),
            clock,
            mode="fast",
            on_epoch_started=store.begin_epoch,
        )
        packets = controller.packets()
        first = next(packets)
        claim = TimelineClaim(
            claim_id="claim-1",
            label="music_present",
            text_ru="Слышна музыка.",
            decision="accepted",
            raw_cosine=0.8,
            margin=0.2,
            evidence_refs=("audio:0-1000",),
            window_ids=("window-1",),
            model_revision="revision-a",
            sample_count=1,
        )
        event = TimelineEvent(
            stream_id=clock.stream_id,
            epoch=first.epoch,
            event_id="event-1",
            revision=1,
            start_ms=0,
            end_ms=1000,
            kind="music_started",
            level="L1",
            state="draft",
            modality_mask={"audio": True, "video": False, "speech": False},
            claims=(claim,),
        )
        store.append(event, expected_revision=0)

        controller.seek(10_000)
        after_seek = next(packets)
        assert after_seek.epoch == 1
        late_revision = replace(event, revision=2, end_ms=2000, supersedes_revision=1)
        try:
            store.append(late_revision, expected_revision=1)
        except StaleRevisionError as error:
            assert "stale event epoch" in str(error)
        else:
            raise AssertionError("late old-epoch writer result was accepted")
        controller.stop()
        packets.close()


def test_simulate_realtime_uses_media_time_and_stops_cleanly() -> None:
    controller = ReplayController(
        str(MEDIA / "video_static_3s.mp4"),
        MediaClock("replay-paced"),
        mode="simulate_realtime",
        speed=100,
    )
    started = time.perf_counter()
    packets = list(controller.packets())
    elapsed_s = time.perf_counter() - started

    assert len(packets) == 30
    assert elapsed_s >= 0.01
    assert elapsed_s < 2
