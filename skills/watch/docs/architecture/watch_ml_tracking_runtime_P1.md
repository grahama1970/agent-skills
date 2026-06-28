# Watch ML Tracking Runtime P1

## Default runtime

Use Ultralytics YOLO plus ByteTrack.

```text
frame source -> YOLO detections -> ByteTrack association -> watch.realtime_track_event.v1 JSONL
```

## Detector/tracker output contract

YOLO/ByteTrack may produce:

- `track_id`
- `detector_label`, such as `person`
- `detector_confidence`
- `tracker_confidence`
- bbox in source-frame coordinates and normalized coordinates
- `media_time_s`
- `frame_ref`

It may not produce named character identity. Named identities belong to the identity verifier and must be fail-closed.

## Verification scheduler

Starting target: 5 FPS per stream.

The scheduler should select no more than one verification sample every 200 ms per stream by default, with per-track cooldown to avoid over-sampling one active track. It should prefer high-quality boxes:

- bbox area above threshold,
- non-truncated crop,
- detector confidence above threshold,
- track age long enough to avoid single-frame ghosts,
- source frame available.

## Event stream durability

Write raw track events to JSONL as append-only runtime evidence. Each event must have:

- `run_id`
- `asset_id`
- `stream_id`
- `track_id`
- `event_index`
- `media_time_s`
- `frame_ref`
- `bbox`
- `detector`
- `tracker`
- `identity_status: OBSERVATION_ONLY`

The overlay adapter may consume the stream live. Persistence should consume validated observations, not browser DOM state.
