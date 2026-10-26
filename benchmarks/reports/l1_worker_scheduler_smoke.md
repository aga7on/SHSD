# Bounded L1 worker smoke

Date: 2026-10-26.

## Change

In standard analysis, `BoundedL1Worker` runs semantic matching, `TemporalEventReducer` updates, and scene-cut signal reduction on one serial worker. Its FIFO lane counts both queued and active jobs against a capacity of four. Embedding results enter the lane in media order; the scene-cut path drains earlier embedding results before enqueuing the cut. Iterative-hypothesis mode stays inline because it shares the text embedding provider.

`EventStore` now opens its SQLite connection with `check_same_thread=False`; all connection operations are already guarded by its `RLock`, which serializes writes from the L1 and speech workers.

## Verification

Ran the 20 s `av_sync_20s.mp4` fixture at L0/L1/L2 with four CPU threads and prefetch capacity eight.

- C/E/R(L1)/R(L2) reached 20,000 ms.
- 36 L1 window matches produced 31 L1 events; 14 L2 events committed.
- The L1 lane submitted 12 jobs, reached a maximum of 2/4 outstanding, and had zero failures.
- The embedding lane completed 9/9 jobs with a maximum of 2/2 outstanding.
- Scheduler rejects: 0. Final load mode: `normal`.
- L1 `window_match` rows stayed in nondecreasing media-time order from 0 to 20,000 ms.
- `pytest tests/unit -q`: 148 passed.

The suite also now checks the implemented URL contract: supported HTTP URLs are accepted through a fake runner, while unsupported schemes remain rejected. This smoke verifies bounded off-consumer L1 work and event order on a finite local source; the single common scheduler, cross-level priorities, physical-camera/reconnect behavior, and sustained live latency remain open.
