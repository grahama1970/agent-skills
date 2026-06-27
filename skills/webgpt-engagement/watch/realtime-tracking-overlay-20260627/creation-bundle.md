# WebGPT Review Bundle: Watch Real-Time Tracking Overlay Rung

## Request

Review the next Watch implementation rung and give concrete corrective guidance. Do not redesign the whole product. The immediate question is whether the new event-derived overlay payload is the right bridge from streamed tracker events to the Watch modal/table overlay, and what the next bounded implementation step should be.

## Objective

Develop Watch as a real-time evidence-stream manager. Movies are the test case; the destination is managing many drones/streams in an AO. The invariant is:

```text
live tracking is streamed
bounded observations and cases are persisted to memory/Qdrant/graph
```

## Current State

Repository: `/home/graham/workspace/experiments/agent-skills`
Branch: `feat/webgpt-no-activate`

Existing Watch artifacts:

- `skills/watch/docs/architecture/watch_realtime_tracking_execution_plan.md`
- `skills/watch/docs/architecture/watch_track_observations.schema.json`
- `skills/watch/scripts/build_realtime_tracking_event_log.py`
- `skills/watch/scripts/build_realtime_tracking_upsert_payloads.py`
- `skills/watch/scripts/track_yolo_bytetrack.py`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_tracker_events/watch_tracker_event_log.bad_santa_marcus.frame_harness.jsonl`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_upsert_payloads/summary.json`

New artifact added this round:

- `skills/watch/scripts/build_tracking_overlay_payload.py`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_overlay_payload/watch_ui_overlay_payload.bad_santa_marcus.json`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_overlay_payload/inspection.md`

## Concrete Command Evidence

```bash
python3 skills/watch/scripts/build_tracking_overlay_payload.py
```

Output:

```text
overlay_payload_ok 1
frame_size 256 140
entities ['Marcus']
payload /home/graham/workspace/experiments/agent-skills/skills/watch/docs/architecture/generated/bad_santa_marcus_0248_overlay_payload/watch_ui_overlay_payload.bad_santa_marcus.json
```

```bash
python3 -m json.tool skills/watch/docs/architecture/generated/bad_santa_marcus_0248_overlay_payload/watch_ui_overlay_payload.bad_santa_marcus.json >/tmp/watch_overlay_payload.validated.json
```

Result: JSON parses.

```bash
python3 - <<'PY'
import json
from pathlib import Path
p=Path('skills/watch/docs/architecture/generated/bad_santa_marcus_0248_overlay_payload/watch_ui_overlay_payload.bad_santa_marcus.json')
data=json.loads(p.read_text())
assert data['schema_version']=='watch.ui_overlay_payload.v1'
assert data['status']=='DRY_RUN_ONLY'
assert data['posted'] is False
assert data['overlay_count']==1
ov=data['overlays'][0]
assert ov['entity']['name']=='Marcus'
assert ov['bbox_percent']['left'] > 0
assert ov['bbox_percent']['width'] > 0
assert ov['source_event_count']==3
print('overlay_contract_ok', data['overlay_count'], ov['entity']['name'], ov['bbox_percent'])
PY
```

Output:

```text
overlay_contract_ok 1 Marcus {'height': 76.429, 'left': 44.141, 'top': 8.571, 'width': 30.859}
```

```bash
python3 scripts/check_mock_evidence_claims.py
```

Output:

```text
OK: checked 297 test file(s); no mock+proof claim violations
```

## Payload Shape

The generated payload contains:

```json
{
  "schema_version": "watch.ui_overlay_payload.v1",
  "status": "DRY_RUN_ONLY",
  "posted": false,
  "overlay_count": 1,
  "frame_size": {"width": 256, "height": 140},
  "overlays": [
    {
      "overlay_id": "watch_overlay_movie_bad_santa_2003_unrated_seg_0007_track_07",
      "asset_uid": "movie_bad_santa_2003_unrated",
      "segment_id": "seg_0007",
      "track_id": "track_07",
      "classification": "provisional_identity",
      "bbox_xyxy": [113, 12, 192, 119],
      "bbox_percent": {"left": 44.141, "top": 8.571, "width": 30.859, "height": 76.429},
      "entity": {
        "entity_id": "movie_domain_entities/marcus_bad_santa_2003",
        "name": "Marcus",
        "kind": "CHARACTER",
        "actor_name": "Tony Cox",
        "confidence": 0.5,
        "status": "PROVISIONAL"
      },
      "source_event_count": 3
    }
  ]
}
```

## Claim Boundary

This is not live ML proof. It proves only that validated Watch track events can drive UI overlay geometry without hard-coded boxes. It does not prove:

- live YOLO/ByteTrack inference
- person re-identification
- character identity
- memory writes
- Qdrant writes
- recall
- production UI consumption of the payload

## Constraints

- Watch rows must preserve frame, playable movie segment, scene marker, SRT, audio audit, and explicit gaps. Do not delete table content to make it look cleaner.
- Brave/movie-domain data provides actor/character priors only. It cannot prove a character is visible in a segment.
- `$memory` pipeline remains `/intent -> extract entities -> /recall -> create evidence case when required -> answer/clarify/deflect`.
- Arango/memory stores metadata, source refs, graph edges, and pointers. Raw vectors must stay out of Arango. Qdrant/Jina stores embeddings.
- Every proof claim must separate mocked/dry-run/live evidence.

## Questions For WebGPT

1. Is `watch.ui_overlay_payload.v1` the right intermediate contract between streamed tracker JSONL and the Watch browser/modal overlay?
2. What fields are missing for real-time drone/AO applicability, especially for many tracks, telemetry overlays, and stale-track expiration?
3. Should the next implementation step wire this payload into the existing Watch UI, or should it first run a live Ultralytics YOLO + ByteTrack adapter on the Bad Santa clip and regenerate this same payload from live events?
4. What minimal acceptance test should gate the next PR so we do not regress into hard-coded boxes or table deletion again?

## Desired Output

Return a concise technical review with:

- verdict: ACCEPT / REVISE / BLOCKED
- required schema changes, if any
- next bounded implementation step
- proof commands/artifacts required before claiming progress
