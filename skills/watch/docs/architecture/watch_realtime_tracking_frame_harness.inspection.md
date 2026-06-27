# Watch Real-Time Tracking Frame Harness Inspection

Status: ACCEPTED
Inspected: 2026-06-27
Artifact directory: `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_tracker_events/`

## Artifact Contract

Artifact: deterministic frame-backed live-track event harness for the Bad Santa
Marcus canary.

Input:

- `watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json`
- representative manifest frame: `/tmp/watch-wex5uxs_/frames/frame_0007.jpg`
- `watch_track_observations.schema.json`

Output:

- `source_frame.jpg`
- `watch_tracker_event_log.bad_santa_marcus.frame_harness.jsonl`
- `summary.json`

Must not:

- claim YOLO/ByteTrack inference
- claim character identity proof
- post to memory
- write Qdrant vectors
- upgrade Brave/movie-domain priors into scene truth

## Inspection Commands

```bash
python3 -m py_compile skills/watch/scripts/build_realtime_tracking_event_log.py
python3 skills/watch/scripts/build_realtime_tracking_event_log.py
```

```bash
python3 - <<'PY'
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from PIL import Image

root = Path('skills/watch/docs/architecture')
schema = json.loads((root / 'watch_track_observations.schema.json').read_text())
event_schema = dict(schema['$defs']['live_track_update_event'])
event_schema['$defs'] = schema['$defs']
out = root / 'generated/bad_santa_marcus_0248_tracker_events'
events_path = out / 'watch_tracker_event_log.bad_santa_marcus.frame_harness.jsonl'
events = []
for index, line in enumerate(events_path.read_text().splitlines(), start=1):
    event = json.loads(line)
    errors = sorted(Draft202012Validator(event_schema).iter_errors(event), key=lambda e: e.path)
    if errors:
        for err in errors:
            print('event_schema_error', index, list(err.path), err.message)
        raise SystemExit(1)
    events.append(event)
with Image.open(out / 'source_frame.jpg') as image:
    print('source_frame', image.size, image.mode)
print('frame_harness_events_ok', len(events))
print('track_ids', sorted({event['track_id'] for event in events}))
print('time_bounds', events[0]['media_time_seconds'], events[-1]['media_time_seconds'])
print('provenance', json.loads((out / 'summary.json').read_text())['provenance'])
PY
```

## Inspection Results

```text
frame_harness_events_ok 3
frame_size 256 140
track_ids ['track_07']
```

```text
source_frame (256, 140) RGB
frame_harness_events_ok 3
track_ids ['track_07']
time_bounds 168.42 191.72
provenance deterministic_frame_harness_not_ml
```

## Acceptance Rationale

The harness is accepted as the next non-writing proof rung because it consumes a
real frame referenced by the Watch manifest and emits the same live-track JSONL
contract used by the dry-run memory payload builder. It keeps the event
provenance explicit and reduces candidate confidence so domain priors cannot
be mistaken for scene truth.

## What This Does Not Prove

- It does not prove person detection.
- It does not prove ByteTrack or DeepSORT continuity.
- It does not prove Marcus is present.
- It does not prove the Watch UI overlay renders.
- It does not prove memory writes or recall.

## Next Legal Move

Replace the deterministic bounding-box harness with a YOLO + ByteTrack adapter
that emits the same `watch.live_track_update.v1` JSONL contract, then compare
the adapter output against this fixture before any memory write.
