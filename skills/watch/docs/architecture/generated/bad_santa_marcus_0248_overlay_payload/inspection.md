# Watch UI Overlay Payload Inspection

Status: `DRY_RUN_ONLY`

Payload: `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_overlay_payload/watch_ui_overlay_payload.bad_santa_marcus.json`

This artifact adapts validated `watch.live_track_update.v1` events into UI
overlay geometry for the Watch table/modal. It is intended to remove hard-coded
annotation boxes from the browser layer.

## Counts

- Overlay count: `1`
- Frame size: `256x140`
- Source events: `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_tracker_events/watch_tracker_event_log.bad_santa_marcus.frame_harness.jsonl`

## Overlays

- `watch_overlay_movie_bad_santa_2003_unrated_seg_0007_track_07`: `Marcus` from `3` events, bbox percent `{'left': 44.141, 'top': 8.571, 'width': 30.859, 'height': 76.429}`

## Claim Boundary

This payload proves only that validated Watch track events can drive browser overlay geometry without hard-coded boxes. It does not prove live YOLO/ByteTrack inference, person re-identification, character identity, memory writes, Qdrant writes, or recall.
