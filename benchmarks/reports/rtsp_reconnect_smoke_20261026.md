# RTSP reconnect smoke — 2026-10-26

## Scenario

One API stream consumed synthetic A/V from a local MediaMTX publisher. The publisher was stopped after epoch 0 had captured 4,009 ms. SHSD detected the interrupted RTSP session, advanced to epoch 1, and resumed after the publisher started again. The stream then ran in epoch 1 and was stopped through the API.

## Result

- Initial capture: epoch 0, C=4,009 ms.
- Capture after publisher restart: epoch 1, C=4,047 ms; API status remained `running`.
- API transport retries: 1. Model/runtime errors are not retried.
- Final stop: `stopped`, no stream error; epoch 1 C/E/R(L1)=11,247 ms.
- Peak process-tree RSS: 2,419,159,040 bytes (2.25 GiB).
- Full API snapshots, metrics, watermarks, and terminal state: [`report.json`](rtsp_reconnect_smoke_20261026/report.json).

The retry policy permits at most five retries, with exponential delay capped at eight seconds. A retry after an active analysis starts a new epoch, and stale callbacks from the prior epoch are ignored. The smoke covers loopback RTSP publisher restart, not physical-camera drivers or a real camera/network outage.
