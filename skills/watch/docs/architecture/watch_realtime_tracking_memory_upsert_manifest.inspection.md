# Watch Real-Time Tracking Memory Upsert Manifest Inspection

Status: ACCEPTED
Inspected: 2026-06-27
Artifact: `skills/watch/docs/architecture/watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json`

## Artifact Contract

Artifact: dry-run memory upsert manifest for the Bad Santa Marcus real-time
tracking canary.

Input:

- `watch_realtime_character_tracking_contract.md`
- `watch_track_observations.schema.json`
- `watch_track_observation.bad_santa_marcus.sample.json`
- `watch_evidence_cases.schema.json`

Output shape:

- one `movie_domain_entities` record
- one bounded `watch_track_observations` record
- one `watch_evidence_cases` record
- graph edges linking case, observation, domain entity, and Qdrant pointer
- Qdrant pointer plan with payload metadata only
- memory `/upsert` request plan
- rollback keys
- recall proof plan
- acceptance gates before live write

Must not include:

- live memory writes
- raw vector arrays in Arango-bound records
- treating Brave Search as scene truth

## Inspection Commands

```bash
python3 - <<'PY'
import json
from pathlib import Path
from jsonschema import Draft202012Validator
root = Path('skills/watch/docs/architecture')
files = [
  root / 'watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json',
  root / 'watch_track_observations.schema.json',
  root / 'watch_track_observation.bad_santa_marcus.sample.json',
  root / 'watch_evidence_cases.schema.json',
]
for path in files:
  json.loads(path.read_text())
  print(f'json_ok {path}')
schema = json.loads((root / 'watch_track_observations.schema.json').read_text())
sample = json.loads((root / 'watch_track_observation.bad_santa_marcus.sample.json').read_text())
errors = sorted(Draft202012Validator(schema).iter_errors(sample), key=lambda e: e.path)
if errors:
  raise SystemExit(1)
print('schema_ok watch_track_observation.bad_santa_marcus.sample.json')
manifest = json.loads((root / 'watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json').read_text())
forbidden = []
def walk(value, path='$'):
  if isinstance(value, dict):
    for key, child in value.items():
      if key.lower() in {'embedding', 'embeddings', 'embedding_visual', 'vector', 'vectors'}:
        forbidden.append(f'{path}.{key}')
      walk(child, f'{path}.{key}')
  elif isinstance(value, list):
    for idx, child in enumerate(value):
      walk(child, f'{path}[{idx}]')
walk(manifest)
if forbidden:
  raise SystemExit(1)
print('no_raw_vector_fields watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json')
print('manifest_counts', {
  key: len(value) if isinstance(value, list) else 'object'
  for key, value in manifest['collections'].items()
})
PY
```

## Inspection Result

```text
json_ok skills/watch/docs/architecture/watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json
json_ok skills/watch/docs/architecture/watch_track_observations.schema.json
json_ok skills/watch/docs/architecture/watch_track_observation.bad_santa_marcus.sample.json
json_ok skills/watch/docs/architecture/watch_evidence_cases.schema.json
schema_ok watch_track_observation.bad_santa_marcus.sample.json
no_raw_vector_fields watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json
manifest_counts {"movie_domain_entities": 1, "watch_evidence_cases": 1, "watch_evidence_edges": 3, "watch_track_observations": 1}
```

## Acceptance Rationale

The manifest is accepted as a dry-run artifact because it makes the memory,
graph, and Qdrant-pointer write plan explicit without executing writes. It
preserves the source-truth boundary: Brave Search creates a domain prior for
`Tony Cox -> Marcus`, while the segment claim remains `INCONCLUSIVE` until
Watch frame/clip/track evidence or human review supports it.

## What This Does Not Prove

- It does not prove live tracker output.
- It does not prove memory writes.
- It does not prove Qdrant point creation.
- It does not prove recall for `find all movie segments with Marcus`.
- It does not prove that Marcus is visually present in the segment.

## Next Legal Move

Create a deterministic tracker-event fixture or playback log that feeds the
same `track_id`/`segment_id` into the dry-run manifest, then execute a dry-run
memory payload builder that emits `/upsert` request JSON without posting it.
