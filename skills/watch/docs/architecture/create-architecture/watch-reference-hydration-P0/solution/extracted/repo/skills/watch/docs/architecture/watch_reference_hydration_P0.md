# Watch Reference Hydration P0 Architecture Contract

## 1. Purpose

`watch-reference-hydration-P0` makes Watch ingest identity-aware video without converting detector labels, web snippets, or movie-domain priors into unsupported scene truth.

The P0 slice introduces a reference-hydration gate before ingest/tracking:

- cinema/movie assets automatically create a cast/character reference-candidate package before ingest starts;
- drone, ITAR, RTSP, and YouTube streams require a source-provided reference manifest or fail closed;
- low-rate tracker observations may stream continuously with stable track ids;
- identity promotion requires approved references, bounded observations, comparison evidence, segment context, persistence receipts, and later `$memory recall` proof.

The current Bad Santa canary remains inconclusive until approved reference images and recall proof exist.

## 2. Source-of-truth boundaries

| Surface | Allowed role | Forbidden role |
|---|---|---|
| Video frame / crop / segment / transcript | Canonical evidence for what was observed in the asset | Cannot name a person without comparison evidence |
| YOLO/ByteTrack track output | Bounded observation proposal and crop source | Cannot identify a named character by itself |
| Movie-domain public search | Candidate source discovery for cast/character references | Cannot prove scene visibility |
| Source-provided drone/stream manifest | Required domain-controlled reference source for restricted or live streams | Cannot be replaced by public web search |
| Approved reference package | Identity prior used in visual/text comparison | Still not scene truth until matched to observations |
| Qdrant/Jina | Vector retrieval and similarity search | Not the authority for raw facts or unsupported identity creation |
| Arango | Structured metadata, graph edges, Qdrant pointers, receipts | Must not store raw vectors |
| `$memory recall` | Official retrieval path for user/agent answers | Must not be bypassed by direct Qdrant/Arango answers |

## 3. Asset policy

### 3.1 Cinema/movie assets

Movie ingest must start by creating a `watch.reference_hydration_plan.v1` using available movie metadata:

- title;
- release year when known;
- asset id / source uri / media digest;
- cast/character candidate source queries;
- candidate source urls and provenance;
- candidate entity names, display names, and ambiguous aliases.

Movie-domain public search is allowed only to collect reference candidates. It does not prove segment visibility. If candidate collection returns zero candidates for an entity, the entity remains unavailable for identity promotion and any corresponding track verification must return `IDENTITY_INCONCLUSIVE`.

Movie tracks may still stream as observations while references are pending approval. Identity promotion remains disabled until approved reference images and embeddings exist.

### 3.2 Drone / ITAR / RTSP / YouTube streams

Non-movie streams must not use public search as a fallback reference hydrator. They require one of:

- source-provided reference manifest;
- source metadata package;
- asset registry entry with approved reference ids;
- channel/operator manifest with signed or otherwise controlled provenance.

When the manifest is absent or invalid, Watch must fail closed before ingest/tracking with `REFERENCE_PACKAGE_MISSING` and must not create identity candidates.

### 3.3 Tracker stream policy

Tracker observations may stream live at a verification cadence such as 5 FPS while preserving continuous `track_id`. Every observation must have deterministic ids linking:

- asset id;
- segment id;
- track id;
- frame index or media time;
- bbox;
- crop hash when a crop exists;
- source event id.

Tracker observations are observation proposals only. They are not identity truth.

## 4. State machine

The P0 state machine is included as:

`skills/watch/docs/architecture/state_machines/watch_reference_hydration_P0.state_machine.json`

Required states:

- `REFERENCE_PACKAGE_MISSING`
- `REFERENCE_CANDIDATES_COLLECTED`
- `REFERENCE_IMAGES_PENDING_APPROVAL`
- `REFERENCE_EMBEDDINGS_READY`
- `TRACK_OBSERVING`
- `IDENTITY_CANDIDATE`
- `IDENTITY_SUPPORTED`
- `IDENTITY_INCONCLUSIVE`
- `IDENTITY_REFUTED`
- `CASE_ANCHOR_CREATED`
- `MEMORY_PERSISTED`
- `RECALL_VERIFIED`

Key state rules:

1. `REFERENCE_PACKAGE_MISSING` is terminal for non-movie stream ingest until a source manifest is provided.
2. `REFERENCE_CANDIDATES_COLLECTED` is allowed for movies from public-source candidate discovery, but does not permit identity promotion.
3. `REFERENCE_IMAGES_PENDING_APPROVAL` permits review and crop/reference comparison preparation only.
4. `REFERENCE_EMBEDDINGS_READY` requires approved references plus deterministic Qdrant point ids or write receipts.
5. `TRACK_OBSERVING` may exist without identity support.
6. `IDENTITY_SUPPORTED` requires a reference package, observation evidence, comparison evidence, transcript/segment context where available, and persistence receipts.
7. `MEMORY_PERSISTED` is not enough to answer a user request; a later `$memory recall` query must produce `RECALL_VERIFIED`.

## 5. Lifecycle flow

### 5.1 Movie flow

1. Normalize asset metadata and compute `asset_id`.
2. Create movie reference-hydration plan.
3. Collect cast/character candidate sources.
4. Cache candidate image/source metadata locally with provenance.
5. Require human or policy approval before any reference is marked approved.
6. Generate reference-image/text embeddings with deterministic Qdrant ids.
7. Start ingest/tracking and extract observations/crops.
8. Compare observation crops/frames against approved references and segment text/transcript.
9. Create identity evidence records.
10. If supported, create bounded evidence-case anchor with `entity_ids` and `time_range`.
11. Persist Arango metadata and Qdrant pointers through `$memory` write/evidence-case semantics.
12. Verify retrieval through `$memory recall`.

### 5.2 Non-movie stream flow

1. Normalize stream asset metadata and compute `asset_id`.
2. Load source manifest.
3. Validate manifest provenance, allowed asset kind, reference ids, approval state, and embedding pointers.
4. If invalid or absent: fail closed with `REFERENCE_PACKAGE_MISSING`.
5. If valid: track live observations at configured cadence.
6. Verify observations only against manifest-approved references and source context.
7. Persist supported or inconclusive trace records with idempotent keys.
8. Require `$memory recall` proof before any downstream answer claims retrieval is working.

## 6. Identity-promotion contract

`IDENTITY_SUPPORTED` requires all of the following:

- observation id and segment id;
- approved reference package id;
- at least one approved reference id;
- crop/frame evidence or a declared frame evidence gap;
- visual comparison score meeting threshold;
- transcript/text/context support when available;
- no refuting evidence above threshold;
- Arango write receipt for metadata;
- Qdrant write receipt or existing deterministic point id for embeddings;
- memory/evidence-case receipt;
- later `$memory recall` proof for entity/time query.

If any required item is missing, the state is `IDENTITY_INCONCLUSIVE` or `IDENTITY_REFUTED`, never `IDENTITY_SUPPORTED`.

## 7. Fail-closed behavior

| Condition | State | Allowed output | Forbidden output |
|---|---|---|---|
| Drone/ITAR/RTSP/YouTube manifest missing | `REFERENCE_PACKAGE_MISSING` | clear error, no identity candidates | public web fallback, ingest/tracking identity path |
| Movie public candidates exist but no approved images | `REFERENCE_IMAGES_PENDING_APPROVAL` | observations, review queue, inconclusive identity | supported identity |
| Detector label only | `IDENTITY_INCONCLUSIVE` | observation trace | named character/person support |
| Brave/movie source only | `IDENTITY_INCONCLUSIVE` | reference candidate provenance | scene visibility proof |
| Qdrant planned but not written | `REFERENCE_IMAGES_PENDING_APPROVAL` or `IDENTITY_INCONCLUSIVE` | planned pointer ids with `PLANNED_NOT_WRITTEN` | recall or persistence claim |
| Arango contains raw vector | validation error | rollback/rebuild | acceptance of write |
| Direct Qdrant/Arango answer path | validation error | force `$memory recall` | user-facing answer |

## 8. Persistence contracts

### 8.1 Deterministic ids

Use canonical JSON serialization, SHA-256 digests, and UUIDv5 point ids.

- `asset_id = watch_asset:<sha256(canonical_source_uri + media_sha256_or_declared_source_id)>`
- `segment_id = watch_segment:<sha256(asset_id + start_ms + end_ms)>`
- `reference_package_id = watch_refpkg:<sha256(asset_id_or_domain + entity_key + package_version)>`
- `reference_item_id = watch_ref:<sha256(reference_package_id + source_uri + image_sha256_or_external_id)>`
- `track_observation_id = watch_obs:<sha256(asset_id + segment_id + track_id + frame_index + media_time_ms + bbox + crop_sha256)>`
- `identity_evidence_id = watch_identity:<sha256(track_observation_id + reference_package_id + approved_reference_ids + verifier_version)>`
- `case_anchor_id = watch_case:<sha256(asset_id + entity_ids + time_range + evidence_ids)>`
- `qdrant_point_id = uuid5(WATCH_NAMESPACE_UUID, canonical_id)`

### 8.2 Arango collections

Arango stores metadata and graph edges only:

- `watch_assets`
- `watch_reference_packages`
- `watch_reference_items`
- `watch_track_observations`
- `watch_identity_evidence`
- `watch_evidence_cases`
- `watch_memory_receipts`

Arango may store Qdrant collection names, point ids, vector model names, dimensions, and write receipts. It must not store raw embedding vectors.

### 8.3 Qdrant collections

Qdrant stores multimodal/text embeddings with deterministic point ids:

- `watch_reference_image_embeddings`
- `watch_track_crop_embeddings`
- `watch_segment_text_embeddings`
- `watch_identity_evidence_embeddings`

Payload must include enough metadata to route recall results back to Arango:

- `asset_id`
- `segment_id`
- `entity_id` or `identity_candidate_id`
- `reference_package_id`
- `reference_item_id` when applicable
- `track_observation_id` when applicable
- `time_range`
- `schema`
- `model`
- `source_sha256`

### 8.4 `$memory` write and recall contract

The Watch skill must preserve the memory pipeline:

`intent -> extract entities -> recall -> create evidence case when needed -> answer/clarify/deflect`

For persistence, Watch prepares bounded write/evidence-case requests. The memory layer owns durable write semantics and recall. Watch must not answer by querying Qdrant or Arango directly. A claim such as "find all movie segments with Willie works" requires a recall proof artifact containing:

- recall query;
- extracted entity ids;
- returned evidence case ids;
- returned segment ids and time ranges;
- citations/source records;
- negative control where applicable.

## 9. Schemas and API contracts

Schema files are included under:

`skills/watch/docs/architecture/schemas/`

Primary schemas:

- `watch_reference_hydration_plan.schema.json`
- `watch_source_reference_manifest.schema.json`
- `watch_reference_package.schema.json`
- `watch_track_observation.schema.json`
- `watch_identity_evidence.schema.json`
- `watch_memory_trace_write.schema.json`

The helper module and CLIs are included under:

- `skills/watch/scripts/watch_reference_hydration.py`
- `skills/watch/scripts/build_watch_reference_hydration_plan.py`
- `skills/watch/scripts/validate_watch_reference_hydration_contract.py`
- `skills/watch/scripts/build_watch_memory_trace_plan.py`

## 10. File-by-file implementation plan

Copy the `repo/` directory from this bundle into the repository root. The solution intentionally avoids touching unrelated dirty UI files.

| Repo-relative path | Action | Purpose |
|---|---|---|
| `skills/watch/docs/architecture/watch_reference_hydration_P0.md` | add | architecture contract in-repo |
| `skills/watch/docs/architecture/state_machines/watch_reference_hydration_P0.state_machine.json` | add | machine-readable lifecycle |
| `skills/watch/docs/architecture/schemas/*.schema.json` | add | payload contracts |
| `skills/watch/scripts/watch_reference_hydration.py` | add | deterministic ids, plan builder, validators, memory trace planner |
| `skills/watch/scripts/build_watch_reference_hydration_plan.py` | add | CLI to build movie/stream hydration plans |
| `skills/watch/scripts/validate_watch_reference_hydration_contract.py` | add | fail-closed validator CLI |
| `skills/watch/scripts/build_watch_memory_trace_plan.py` | add | CLI to create planned memory write/evidence-case payloads |
| `skills/watch/tests/test_watch_reference_hydration_P0.py` | add | P0 contract tests |
| `skills/watch/tests/fixtures/reference_hydration_P0/*.json` | add | movie, stream, observation, identity fixtures |
| `skills/watch/docs/architecture/patches/watch_reference_hydration_P0_docs.patch` | optional apply | minimal doc additions for existing README/project/execution docs |

## 11. Exact local commands

From repo root after copying `repo/` contents:

```bash
python3 -m py_compile \
  skills/watch/scripts/watch_reference_hydration.py \
  skills/watch/scripts/build_watch_reference_hydration_plan.py \
  skills/watch/scripts/validate_watch_reference_hydration_contract.py \
  skills/watch/scripts/build_watch_memory_trace_plan.py

python3 skills/watch/scripts/build_watch_reference_hydration_plan.py \
  --asset skills/watch/tests/fixtures/reference_hydration_P0/asset_movie_bad_santa.json \
  --reference-candidates skills/watch/tests/fixtures/reference_hydration_P0/movie_reference_candidates_bad_santa.json \
  --out /tmp/watch_movie_reference_hydration_plan.json

python3 skills/watch/scripts/validate_watch_reference_hydration_contract.py \
  --plan /tmp/watch_movie_reference_hydration_plan.json

python3 skills/watch/scripts/build_watch_reference_hydration_plan.py \
  --asset skills/watch/tests/fixtures/reference_hydration_P0/asset_drone_stream.json \
  --out /tmp/watch_drone_missing_manifest_plan.json

python3 skills/watch/scripts/validate_watch_reference_hydration_contract.py \
  --plan /tmp/watch_drone_missing_manifest_plan.json \
  --expect-fail-closed

python3 skills/watch/scripts/build_watch_reference_hydration_plan.py \
  --asset skills/watch/tests/fixtures/reference_hydration_P0/asset_drone_stream.json \
  --source-manifest skills/watch/tests/fixtures/reference_hydration_P0/source_reference_manifest_drone_valid.json \
  --out /tmp/watch_drone_reference_hydration_plan.json

python3 skills/watch/scripts/build_watch_memory_trace_plan.py \
  --asset skills/watch/tests/fixtures/reference_hydration_P0/asset_movie_bad_santa.json \
  --observations skills/watch/tests/fixtures/reference_hydration_P0/track_observations_bad_santa_0248.json \
  --identity-evidence skills/watch/tests/fixtures/reference_hydration_P0/identity_evidence_inconclusive_domain_only.json \
  --out /tmp/watch_memory_trace_plan.json

pytest -q skills/watch/tests/test_watch_reference_hydration_P0.py
```

Proof artifacts before claiming progress:

- generated movie hydration plan;
- generated non-movie fail-closed plan;
- generated source-manifest-backed stream plan;
- generated memory trace plan with `PLANNED_NOT_WRITTEN` write status;
- pytest output;
- explicit note that current canary still has `supported_count = 0` and no recall proof.

## 12. Rollback and rebuild

Rollback is safe because all new runtime writes are planned and idempotent in P0.

```bash
rm -f skills/watch/scripts/watch_reference_hydration.py
rm -f skills/watch/scripts/build_watch_reference_hydration_plan.py
rm -f skills/watch/scripts/validate_watch_reference_hydration_contract.py
rm -f skills/watch/scripts/build_watch_memory_trace_plan.py
rm -rf skills/watch/docs/architecture/schemas
rm -rf skills/watch/docs/architecture/state_machines
rm -f skills/watch/docs/architecture/watch_reference_hydration_P0.md
rm -rf skills/watch/tests/fixtures/reference_hydration_P0
rm -f skills/watch/tests/test_watch_reference_hydration_P0.py
```

Rebuild:

```bash
git checkout -- skills/watch || true
cp -a <bundle>/repo/. .
python3 -m py_compile skills/watch/scripts/watch_reference_hydration.py
pytest -q skills/watch/tests/test_watch_reference_hydration_P0.py
```

If a future implementation writes Qdrant/Arango, every write must record rollback receipts before mutation. P0 does not write vectors or graph records.

## 13. Known gaps deliberately left open

- No live YOLO/ByteTrack runtime is claimed by this package.
- No approved movie reference images are invented.
- No Qdrant or Arango write is claimed.
- No `$memory recall` proof is claimed.
- No Watch UI redesign is included.
- No drone AO command system is included.

## 14. Bounded next implementation step

Implement the repo-relative files in this bundle, run the commands above, and then connect the new movie hydration CLI to the Watch ingest preflight path. The next claim should be limited to:

> Watch can produce deterministic reference-hydration plans for movie assets, fail closed for stream assets without source manifests, and generate planned memory trace payloads without promoting identity.

Do not claim live identity support or recall until approved references are embedded and `$memory recall` proves retrieval.
