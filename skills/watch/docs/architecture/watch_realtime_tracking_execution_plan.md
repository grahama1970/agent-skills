# Watch Real-Time Tracking Execution Plan

Status: active implementation plan
Created: 2026-06-27
Scope: movie-character tracking canary for multi-drone AO stream management

## Objective

Make Watch prove the same loop on movie characters that it will later use for
many drone or sensor streams in an area of operations:

```text
stream provisional ML tracks live
hydrate domain entities separately
verify against extracted Watch evidence
persist only bounded observations, cases, graph edges, and vector pointers
answer through the memory pipeline
```

Movies remain the controlled canary. They are easier to inspect than AO feeds,
but they must use the same evidence boundaries: domain knowledge is a prior,
not scene truth.

## Current Inputs

| Artifact | Current status | Role |
| --- | --- | --- |
| `watch_realtime_character_tracking_contract.md` | Candidate contract | Architecture boundary and evidence rules |
| `watch_track_observations.schema.json` | Draft schema exists | Bounded observation persistence contract |
| `watch_evidence_cases.schema.json` | Draft schema exists | Durable case and overlay contract |
| `watch_tracker_event_log.bad_santa_marcus.fixture.jsonl` | Deterministic fixture exists | Offline live-track event shape proof |
| `build_realtime_tracking_event_log.py` | Deterministic harness exists | Emits schema-valid event JSONL from fixture frame |
| `track_yolo_bytetrack.py` | Live bounded run exists | Maps Ultralytics YOLO + ByteTrack output into Watch events |
| `generated/bad_santa_marcus_0248_yolo_bytetrack/` | Live event artifact exists | 80 schema-valid provisional YOLO/ByteTrack events over 168.0-174.46s |
| `generated/bad_santa_marcus_0248_yolo_overlay_payload/` | Live-derived overlay artifact exists | 10 schema-valid overlay records generated from live YOLO event geometry |
| `bad_santa_domain_seed/brave_bad_santa_cast_search.json` | Raw Brave Search seed exists | Movie-domain source candidates only |
| `bad_santa_marcus_0248_upsert_payloads/` | Dry-run payloads exist | `/upsert` request body proof; no live write |

## Non-Negotiable Invariants

1. Brave Search and movie databases seed domain candidates only.
2. A character can be marked present in a segment only from Watch evidence:
   frame, clip, transcript, VLM row text, live track event, human overlay, or
   accepted bounded observation.
3. Memory receives bounded summaries, not every frame.
4. Arango-bound documents store metadata, source refs, graph edges, and Qdrant
   point pointers. They must not store raw vector arrays.
5. Qdrant/Jina multimodal points represent frame crops, scene markers,
   transcript snippets, and optional clip-level features.
6. UI overlays may be provisional. Persistence must name whether identity is
   `CANDIDATE`, `SUPPORTED`, `REFUTED`, or `INCONCLUSIVE`.
7. AO/drone streams use the same model, replacing movie cast/domain priors with
   asset registry, mission logs, telemetry, geofence, sensor state, or operator
   overlays.

## Execution Phases

### Phase 0: Domain / Reference Hydration

Goal: make identity references available before frame extraction or live
tracking starts.

Default by stream type:

| Stream type | Reference source |
| --- | --- |
| Cinema/movie | Brave/movie-domain cast search plus local movie-domain memory |
| YouTube/web | Channel/video metadata, provided annotations, then web search fallback |
| Drone/ITAR/RTSP | Mission manifest, asset registry, telemetry manifest, operator annotations |

For cinema ingest, this phase is mandatory by default. It should produce:

- movie-domain entities such as actor/character pairs
- reference-source candidates with URLs and provenance
- approved reference image slots
- Qdrant/Jina point plans for reference images and later track crops
- failure codes when references are missing

The phase must not prove scene presence. It only creates priors and reference
inputs for later crop/reference comparison.

Current Bad Santa canary:

- Brave Search queries: `3`
- Raw reference-source results: `15`
- Marcus-linked reference query groups: `2`
- Candidate URLs linked to Marcus review crops: `10`
- Approved reference images: `0`
- Qdrant writes: `PLANNED_NOT_WRITTEN`

### Phase 1: Domain Seed Package

Goal: create movie-domain priors without making scene claims.

Inputs:

- Raw Brave Search results:
  `generated/bad_santa_domain_seed/brave_bad_santa_cast_search.json`
- Manual extraction target:
  `movie_domain_entities`

Output records:

- `movie_domain_assets/movie_bad_santa_2003_unrated`
- `movie_domain_entities/willie_bad_santa_2003`
- `movie_domain_entities/marcus_bad_santa_2003`
- `movie_domain_entities/the_kid_bad_santa_2003`

Acceptance evidence:

- Raw Brave Search artifact exists.
- Extracted domain entities cite source URLs.
- Domain records are marked `DOMAIN_PRIOR`.
- No Watch segment claims are emitted from this phase.

### Phase 2: Live Track Event Stream

Goal: produce provisional track events during playback or recorded replay.

Runtime path:

```text
video/stream source
  -> Ultralytics YOLO person/object detection
  -> ByteTrack track IDs
  -> 5fps Watch event sampling/throttle
  -> watch.live_track_update.v1 events
  -> browser/player overlay and active row sync
```

Output:

- JSONL event stream with `stream_id`, `asset_uid`, `segment_id`,
  `media_time_seconds`, `track_id`, `bbox_xyxy`, `detected_class`,
  `candidate_entities`, and `status`.
- The default live canary event cadence is 5fps (`--sample-fps 5`). The tracker
  may process source video internally, but Watch emits and verifies track events
  at this cadence before any bounded observation is persisted.

Acceptance evidence:

- `track_yolo_bytetrack.py --sample-fps 5` runs against a real clip or stream
  source with the `tracking` extra installed.
- Event JSONL validates against `watch_track_observations.schema.json`
  `live_track_update_event`.
- UI modal/table overlay uses actual event bbox data, not a hard-coded region.
- Event claims remain `PROVISIONAL`.

Current canary proof:

- Command: `uv run --extra tracking python scripts/track_yolo_bytetrack.py --model yolo11n.pt --tracker bytetrack.yaml --sample-fps 5 --attach-domain-candidate --max-events 80`
- Output: `yolo_bytetrack_events_ok 80`
- Event log: `generated/bad_santa_marcus_0248_yolo_bytetrack/watch_tracker_event_log.bad_santa_marcus.yolo_bytetrack.jsonl`
- Schema validation: 80 events, 10 track IDs, time bounds 168.0-174.46s, candidate `Marcus`, status `PROVISIONAL`
- Boundary: this proves live event emission and schema validity only. It does
  not prove Marcus identity, UI real-time overlay updates, memory writes,
  Qdrant writes, or recall.

Current overlay proof:

- Command: `python3 scripts/build_tracking_overlay_payload.py --events docs/architecture/generated/bad_santa_marcus_0248_yolo_bytetrack/watch_tracker_event_log.bad_santa_marcus.yolo_bytetrack.jsonl --event-summary docs/architecture/generated/bad_santa_marcus_0248_yolo_bytetrack/summary.json --out-dir docs/architecture/generated/bad_santa_marcus_0248_yolo_overlay_payload`
- Validation: `overlay_payload_schema_ok 10 geometry_plumbing`
- Frame size: `512x278`, derived from the local clip via `ffprobe` because the live YOLO summary does not include `frame_size`
- Boundary: this proves live event geometry can feed the browser overlay payload contract. It does not prove real-time UI animation, Marcus identity, memory writes, Qdrant writes, or recall. The generated payload currently labels all 10 tracks with the same provisional `Marcus` candidate, which is a known identity-verification gap and must stay visually provisional.

### Phase 3: Verification and Bounded Observation

Goal: convert live events into memory-ready segment observations.

Verification compares:

- tracker events
- movie-domain entity priors
- Watch frame/clip/VLM row text
- SRT/Whisper transcript
- human overlay approvals or corrections

Output:

- `watch_track_observations` documents, one per bounded track/segment claim.

Verdict rule:

| Evidence state | Observation status |
| --- | --- |
| Tracker + row evidence agree and identity is supported | `SUPPORTED` |
| Tracker/domain candidate conflicts with row evidence | `REFUTED` or `INCONCLUSIVE` |
| Tracker exists but identity evidence is weak | `INCONCLUSIVE` + `TRACK_IDENTITY_UNCERTAIN` |
| Domain source exists but no Watch evidence supports scene presence | `INCONCLUSIVE` + `COVERAGE_GAP` |

Acceptance evidence:

- Dry-run payload validates.
- Live `/upsert` receipt exists when approved.
- Recall can retrieve the observation by entity and time range.

### Phase 4: Evidence Case Creation

Goal: create durable cases only when there is a real investigative need.

Case triggers:

- operator clicks isolate/create case
- tracker identity conflicts with SRT/Whisper/domain evidence
- AO telemetry conflicts with visual evidence
- answer pipeline needs durable anchoring
- repeated divergence suggests batch resolution or human review

Output:

- `watch_evidence_cases`
- `watch_evidence_edges`
- optional `watch_overlay_records`

Acceptance evidence:

- Case has `entity_ids` and `time_range`.
- Case references source evidence and any track observation.
- Case verdict uses `SUPPORTED`, `REFUTED`, or `INCONCLUSIVE`.
- Technical ingest states use `failure_codes`, not verdict vocabulary.

### Phase 5: Qdrant/Jina Multimodal Index

Goal: support recall such as "find all segments with Willie" across assets.

Point types:

- representative frame crop
- scene marker frame
- transcript/SRT/Whisper chunk
- VLM description chunk
- optional short clip embedding

Arango record fields:

```json
{
  "qdrant_collection": "watch_multimodal",
  "qdrant_point_id": "movie_bad_santa_2003_seg_0007_track_07_frame_crop",
  "embedding_model": "jina-clip-or-current-watch-multimodal-model",
  "embedding_version": "pending",
  "modality": "frame_crop",
  "source_hash": "sha256:..."
}
```

Acceptance evidence:

- Qdrant point exists for at least one crop/text pair.
- Arango document stores pointer metadata only.
- `/recall` result includes `scores.dense > 0.0` for at least one Watch item
  when Qdrant is healthy.

### Phase 6: Chat Memory Pipeline

Goal: answer through the same memory front door that other domains use.

Pipeline:

```text
/intent
extract entities
/recall
create evidence case, if needed
/answer | /clarify | /deflect
```

UI requirement:

- This pipeline belongs in the Watch Agent chat thinking/status line.
- It does not belong in the Library ingest pipeline panel.
- Thinking text must advance with the active memory stage.

Acceptance evidence:

- Asking "find all movie segments with Willie" routes to
  `watch_evidence_recall`.
- Recall inspects Watch collections and returns source refs.
- If evidence is weak, the answer is `CLARIFY` or `INCONCLUSIVE`, not guessed.

## AO / Drone Mapping

| Movie canary concept | AO/drone equivalent |
| --- | --- |
| Movie asset | Mission stream or sensor asset |
| Character domain entity | Asset, vehicle, operator, target, facility, object class |
| SRT stream | Mission plan, telemetry log, operator transcript, ROE event log |
| Whisper stream | Live audio/comms transcript |
| Scene marker frame | Sensor frame or keyframe |
| Track observation | Object/asset track observation |
| Movie-domain cast prior | Asset registry, mission manifest, geofence, order of battle |
| Case | Audit incident, compliance discrepancy, spoof/tamper investigation |

The same fail-closed rule applies: telemetry/domain data can say what should be
there, but only stream evidence can support what is visible at a specific time.

## Next Legal Implementation Move

1. Install the `tracking` extra in a controlled runtime.
2. Run `track_yolo_bytetrack.py --sample-fps 5` against the Bad Santa
   02:48-03:12 clip or an equivalent local stream source.
3. Validate emitted JSONL against the live event schema.
4. Build a UI overlay payload from the live JSONL and repeat positive/negative
   modal proofs against the loaded Watch API/static report artifact.
   - Dry-run adapter exists:
     `scripts/build_tracking_overlay_payload.py`
   - Payload schema and validator exist:
     `docs/architecture/watch_ui_overlay_payload.schema.json` and
     `scripts/validate_watch_overlay_payload.py`
   - Loaded dry-run UI consumption inspection:
     `docs/architecture/watch_ui_overlay_payload_consumption.inspection.md`
   - This still proves event-to-overlay geometry only until the source JSONL is
     produced by live YOLO/ByteTrack.
5. With human approval, post the already generated `/upsert` payloads to memory
   or regenerate them from the live event log.
6. Run recall proof queries:
   - "find all movie segments with Marcus"
   - "find all movie segments with Willie"
7. Record the proof artifacts and update the inspection status.

## Explicit Non-Completion

This plan does not claim the goal is complete. Missing proof remains:

- live YOLO/ByteTrack run
- live memory write receipt
- live `/recall` proof for Watch observations/cases
- Qdrant/Jina point write and dense recall proof
- committed production UI consumption of loaded event-derived overlay payload,
  followed by live stream event consumption
