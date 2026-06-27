# Watch Tracker Event Log Fixture Inspection

Status: ACCEPTED
Inspected: 2026-06-27
Artifact: `skills/watch/docs/architecture/watch_tracker_event_log.bad_santa_marcus.fixture.jsonl`

## Artifact Contract

Artifact: deterministic tracker-event JSONL fixture for the Bad Santa Marcus
real-time tracking canary.

Input:

- `watch_track_observations.schema.json` `$defs.live_track_update_event`
- `watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json`

Output shape:

- JSONL stream of `watch.live_track_update.v1` events
- stable `stream_id`, `asset_uid`, `segment_id`, and `track_id`
- timestamped `bbox_xyxy` updates over the 02:48-03:12 segment
- Marcus candidate entity with Brave/domain prior basis

Must not include:

- final identity verdict
- memory writes
- raw vector arrays
- claim that the fixture is a live model output

## Inspection Commands

```bash
python3 - <<'PY'
import json
from pathlib import Path
from jsonschema import Draft202012Validator
root = Path('skills/watch/docs/architecture')
schema = json.loads((root / 'watch_track_observations.schema.json').read_text())
event_schema = dict(schema['$defs']['live_track_update_event'])
event_schema['$defs'] = schema['$defs']
fixture = root / 'watch_tracker_event_log.bad_santa_marcus.fixture.jsonl'
events = []
for index, line in enumerate(fixture.read_text().splitlines(), start=1):
    event = json.loads(line)
    errors = sorted(Draft202012Validator(event_schema).iter_errors(event), key=lambda e: e.path)
    if errors:
        for err in errors:
            print('event_schema_error', index, list(err.path), err.message)
        raise SystemExit(1)
    events.append(event)
assert len(events) == 3
assert {event['track_id'] for event in events} == {'track_07'}
assert events[0]['media_time_seconds'] < events[-1]['media_time_seconds']
assert events[-1]['status'] == 'BOUNDARY_CANDIDATE'
print('jsonl_events_ok', len(events))
print('track_ids', sorted({event['track_id'] for event in events}))
print('time_bounds', events[0]['media_time_seconds'], events[-1]['media_time_seconds'])
PY
```

## Inspection Result

```text
jsonl_events_ok 3
track_ids ['track_07']
time_bounds 168.42 191.72
```

## Acceptance Rationale

The fixture is accepted as a deterministic stream input because it exercises
the live `track_update` event contract that the dry-run memory manifest consumes.
It keeps the identity provisional and bounded to the segment, which preserves
the Watch rule that Brave/domain priors do not become scene truth.

## What This Does Not Prove

- It does not prove a YOLO/ByteTrack runtime is running.
- It does not prove overlay rendering in the Watch UI.
- It does not prove memory writes or recall.
- It does not prove Marcus is visually present.

## Next Legal Move

Implement a dry-run payload builder that reads this JSONL fixture plus the
accepted manifest and emits concrete `/upsert` request bodies without posting
them.
