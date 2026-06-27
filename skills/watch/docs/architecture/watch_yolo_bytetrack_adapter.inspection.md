# Watch YOLO + ByteTrack Adapter Inspection

Status: ACCEPTED_AS_CONTRACT_ADAPTER
Inspected: 2026-06-27
Adapter: `skills/watch/scripts/track_yolo_bytetrack.py`

## Artifact Contract

Artifact: live-ML adapter that uses Ultralytics YOLO tracking mode with
ByteTrack and emits the existing `watch.live_track_update.v1` JSONL contract.

Input:

- video file, RTSP stream, web stream, or manifest clip path
- `watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json`
- `watch_track_observations.schema.json`
- optional movie-domain candidate from the manifest

Output:

- `watch_tracker_event_log.bad_santa_marcus.yolo_bytetrack.jsonl`
- `summary.json`

Must not:

- write memory
- write Qdrant vectors
- treat YOLO person detections as character identity
- treat Brave/movie-domain priors as scene truth
- create a final evidence case without the bounded verification pass

## Runtime Contract

Install the tracking extra before live use:

```bash
cd skills/watch
uv pip install -e '.[tracking]'
```

Run against the manifest clip:

```bash
python3 scripts/track_yolo_bytetrack.py \
  --model yolo26n.pt \
  --tracker bytetrack.yaml \
  --sample-fps 5 \
  --attach-domain-candidate
```

`--attach-domain-candidate` only attaches provisional domain candidates to the
event stream. It does not verify the character identity.

`--sample-fps` defaults to `5.0` for the Watch canary. It controls the cadence
of Watch track events and the Ultralytics `vid_stride` value. The live overlay
may update continuously, but memory persistence must still summarize bounded
track windows, not every sampled frame.

## Inspection Commands

```bash
python3 -m py_compile skills/watch/scripts/track_yolo_bytetrack.py
```

```bash
python3 - <<'PY'
import importlib.util
import json
from pathlib import Path
from jsonschema import Draft202012Validator

script = Path('skills/watch/scripts/track_yolo_bytetrack.py')
spec = importlib.util.spec_from_file_location('track_yolo_bytetrack', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
manifest = json.loads(Path('skills/watch/docs/architecture/watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json').read_text())
observation = manifest['collections']['watch_track_observations'][0]

class TensorLike:
    def __init__(self, value):
        self.value = value
    def detach(self):
        return self
    def cpu(self):
        return self
    def numpy(self):
        return self
    def tolist(self):
        return self.value

class Boxes:
    id = TensorLike([7.0])
    xyxy = TensorLike([[10.2, 20.7, 100.4, 121.6]])
    cls = TensorLike([0.0])
    conf = TensorLike([0.91])

class Result:
    boxes = Boxes()

events = list(module._events_from_results([Result(), Result()], observation=observation, fps=24.0, frame_stride=5, max_events=10, attach_domain_candidate=True))
schema = json.loads(Path('skills/watch/docs/architecture/watch_track_observations.schema.json').read_text())
event_schema = dict(schema['$defs']['live_track_update_event'])
event_schema['$defs'] = schema['$defs']
validator = Draft202012Validator(event_schema)
for index, event in enumerate(events, start=1):
    errors = sorted(validator.iter_errors(event), key=lambda e: e.path)
    if errors:
        for error in errors:
            print('event_schema_error', index, list(error.path), error.message)
        raise SystemExit(1)
assert len(events) == 3, len(events)
assert events[0]['media_time_seconds'] == 168.0
assert events[1]['media_time_seconds'] == 168.21
assert events[0]['track_id'] == 'track_7'
assert events[-1]['status'] == 'BOUNDARY_CANDIDATE'
assert events[0]['candidate_entities'][0]['name'] == 'Marcus'
print('fake_yolo_adapter_events_ok', len(events))
print('track_ids', sorted({event['track_id'] for event in events}))
print('statuses', [event['status'] for event in events])
print('media_times', [event['media_time_seconds'] for event in events])
print('first_bbox', events[0]['bbox_xyxy'])
print('sample_fps_stride', module._frame_stride(fps=24.0, sample_fps=5.0))
PY
```

## Inspection Results

```text
fake_yolo_adapter_events_ok 3
track_ids ['track_7']
statuses ['PROVISIONAL', 'PROVISIONAL', 'BOUNDARY_CANDIDATE']
media_times [168.0, 168.21, 168.21]
first_bbox [10, 21, 100, 122]
sample_fps_stride 5
```

Local dependency check:

```text
ultralytics_unavailable ModuleNotFoundError No module named 'ultralytics'
cv2_available 4.13.0
```

## Acceptance Rationale

The adapter is accepted as a contract adapter because its Ultralytics result
mapping emits schema-valid Watch live-track events, preserves provisional
candidate identity semantics, and leaves memory writes outside the runtime.

This inspection used fake Ultralytics-style result objects because the local
environment did not have `ultralytics` installed. That proves mapper/schema
wiring only, not live inference.

## What This Does Not Prove

- It does not prove `ultralytics` is installed in the runtime.
- It does not prove YOLO inference.
- It does not prove ByteTrack continuity.
- It does not prove Marcus is present in the clip.
- It does not prove Watch UI overlay rendering.
- It does not prove memory/Qdrant writes or recall.

## Next Legal Move

Install the tracking extra in a controlled runtime, run the adapter against the
manifest clip, and compare the live JSONL output against the deterministic frame
harness before memory writes are approved.
