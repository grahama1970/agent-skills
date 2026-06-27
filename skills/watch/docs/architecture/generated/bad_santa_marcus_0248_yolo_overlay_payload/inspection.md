# Watch UI Overlay Payload Inspection

Status: `DRY_RUN_ONLY`

Payload: `docs/architecture/generated/bad_santa_marcus_0248_yolo_overlay_payload/watch_ui_overlay_payload.bad_santa_marcus.json`

This artifact adapts validated `watch.live_track_update.v1` events into UI
overlay geometry for the Watch table/modal. It is intended to remove hard-coded
annotation boxes from the browser layer.

## Counts

- Overlay count: `10`
- Frame size: `512x278`
- Source events: `docs/architecture/generated/bad_santa_marcus_0248_yolo_bytetrack/watch_tracker_event_log.bad_santa_marcus.yolo_bytetrack.jsonl`

## Overlays

- `watch_overlay_movie_bad_santa_2003_unrated_seg_0007_track_1`: `Marcus` from `8` events, bbox percent `{'left': 3.516, 'top': 0.0, 'width': 55.469, 'height': 91.727}`
- `watch_overlay_movie_bad_santa_2003_unrated_seg_0007_track_10`: `Marcus` from `4` events, bbox percent `{'left': 0.0, 'top': 8.633, 'width': 10.547, 'height': 66.187}`
- `watch_overlay_movie_bad_santa_2003_unrated_seg_0007_track_15`: `Marcus` from `1` events, bbox percent `{'left': 47.461, 'top': 26.259, 'width': 15.43, 'height': 70.504}`
- `watch_overlay_movie_bad_santa_2003_unrated_seg_0007_track_2`: `Marcus` from `30` events, bbox percent `{'left': 54.297, 'top': 0.0, 'width': 43.164, 'height': 98.921}`
- `watch_overlay_movie_bad_santa_2003_unrated_seg_0007_track_3`: `Marcus` from `6` events, bbox percent `{'left': 0.0, 'top': 8.633, 'width': 13.086, 'height': 31.655}`
- `watch_overlay_movie_bad_santa_2003_unrated_seg_0007_track_4`: `Marcus` from `8` events, bbox percent `{'left': 78.516, 'top': 21.223, 'width': 21.484, 'height': 75.18}`
- `watch_overlay_movie_bad_santa_2003_unrated_seg_0007_track_5`: `Marcus` from `5` events, bbox percent `{'left': 26.953, 'top': 7.914, 'width': 24.609, 'height': 44.245}`
- `watch_overlay_movie_bad_santa_2003_unrated_seg_0007_track_6`: `Marcus` from `12` events, bbox percent `{'left': 27.344, 'top': 7.554, 'width': 27.734, 'height': 90.288}`
- `watch_overlay_movie_bad_santa_2003_unrated_seg_0007_track_7`: `Marcus` from `1` events, bbox percent `{'left': 46.875, 'top': 25.899, 'width': 14.258, 'height': 17.986}`
- `watch_overlay_movie_bad_santa_2003_unrated_seg_0007_track_8`: `Marcus` from `5` events, bbox percent `{'left': 76.758, 'top': 18.705, 'width': 8.398, 'height': 35.252}`

## Claim Boundary

This payload proves only that validated Watch track events can drive browser overlay geometry without hard-coded boxes. It does not prove live YOLO/ByteTrack inference, person re-identification, character identity, memory writes, Qdrant writes, or recall.

When the source event log is produced by a live tracker, live detector/tracker
proof remains owned by that source event artifact. This overlay payload only
proves that validated events can be transformed into browser geometry. Identity
labels remain provisional until a separate verification pass supports or
rejects them.
