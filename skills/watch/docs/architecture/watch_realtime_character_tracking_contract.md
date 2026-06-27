# Watch Real-Time Character Tracking Contract

Status: candidate architecture artifact
Created: 2026-06-27
Scope: movie-character tracking as the canary for multi-drone AO stream management

## Purpose

Watch must manage many time-based evidence streams. Movies are the controlled
test case; the destination architecture is many drone, telemetry, industrial,
web, and cinema streams in an area of operations.

The core contract is:

```text
live tracking is streamed
bounded observations and cases are stored to memory
```

The UI may show provisional character labels in real time, but durable memory
records must be segment-bounded, source-grounded, and explicitly marked as
candidate, supported, refuted, inconclusive, or needing review.

## Non-Negotiable Boundaries

1. Brave Search and movie-domain memory provide domain priors, not scene truth.
2. Frame, clip, transcript, telemetry, and audio evidence remain immutable.
3. Corrections are overlays and cases, not source mutations.
4. Memory is not a frame-by-frame dump. Memory stores sampled observations,
   track summaries, identity assertions, retrieval pointers, and cases.
5. Qdrant stores multimodal vectors. Arango/memory stores metadata, graph
   edges, source pointers, and case records.
6. A live overlay label is provisional unless a persisted observation or case
   states its evidence basis.

## Stream Model

All inputs become an `EvidenceStream`:

```json
{
  "stream_id": "watch_stream_bad_santa_2003",
  "asset_uid": "movie_bad_santa_2003_unrated",
  "stream_type": "cinema_srt",
  "source_uri": "/mnt/storage12tb/media/movies/Bad Santa (2003)/Bad.Santa.Unrated.2003.BRRip.XvidHD.720p-NPW.avi",
  "domain_collection": "movie_domain_assets",
  "clock": {
    "mode": "media_time",
    "zero_timestamp": "00:00:00.000"
  }
}
```

For drone and AO streams, the same shape applies with `stream_type` values such
as `drone_telemetry`, `rtsp_live`, `itar_sensor`, or `web_video`, and the clock
uses mission or wall time.

## Live ML Pipeline

### Tier 1: Fast-Path Tracking

Runtime: Python service or browser-adjacent worker.

Recommended starting stack:

- `ultralytics` YOLO for person/object detection.
- ByteTrack or DeepSORT for frame-to-frame track identity.
- OpenCV for decode, frame sampling, and local media I/O.
- Optional face/person re-identification embedding for character assignment.

Fast-path output is streamed to the UI and is allowed to be provisional:

```json
{
  "event_type": "track_update",
  "stream_id": "watch_stream_bad_santa_2003",
  "segment_id": "seg_0007",
  "media_time_seconds": 168.42,
  "track_id": "track_07",
  "bbox_xyxy": [418, 96, 704, 492],
  "class": "person",
  "candidate_entities": [
    {
      "entity_id": "movie_domain_entities/marcus",
      "label": "Marcus",
      "confidence": 0.82,
      "basis": ["reid_embedding", "domain_prior"]
    }
  ],
  "status": "PROVISIONAL"
}
```

The UI should consume these events for overlays, active row sync, and live
operator feedback. These events are not enough by themselves to create a
final case.

### Tier 2: Verification Pass

The Watch Agent consumes live track updates and compares them against:

- movie-domain memory seeded from Brave Search and accepted sources
- extracted Watch rows: frame, clip, transcript, SRT, Whisper, VLM scene text
- user-approved overlays
- for AO streams: mission plan, telemetry, geofence, asset registry, ROE, or
  sensor logs

Verification output is segment-bounded:

```json
{
  "record_type": "watch_track_observation",
  "schema_version": "watch.track_observation.v1",
  "stream_id": "watch_stream_bad_santa_2003",
  "asset_uid": "movie_bad_santa_2003_unrated",
  "segment_id": "seg_0007",
  "track_id": "track_07",
  "time_range": {
    "start": "02:48",
    "end": "03:12",
    "start_seconds": 168,
    "end_seconds": 192
  },
  "candidate_entity": {
    "entity_id": "movie_domain_entities/marcus",
    "name": "Marcus",
    "kind": "CHARACTER",
    "actor_name": "Tony Cox",
    "confidence": 0.82,
    "status": "CANDIDATE"
  },
  "evidence_basis": {
    "frame_refs": ["watch_frame_bad_santa_0007_168s"],
    "clip_refs": ["watch_clip_bad_santa_0007"],
    "transcript_refs": ["watch_content/seg_0007"],
    "qdrant_refs": ["qdrant://watch_multimodal/movie_bad_santa_2003/seg_0007"],
    "domain_refs": ["movie_domain_entities/marcus"]
  },
  "decision": {
    "verdict": "INCONCLUSIVE",
    "failure_codes": ["NEEDS_HUMAN_REVIEW"],
    "reason": "Live tracker candidate is plausible but has not been human-approved."
  }
}
```

### Tier 3: Case Creation

A `watch_evidence_case` is created only when one of these triggers fires:

- visual track conflicts with SRT/Whisper speaker or dialogue attribution
- visual track conflicts with domain memory
- domain search resolves an entity that extracted evidence cannot ground
- stream telemetry conflicts with visual evidence
- operator clicks Isolate/Create Case
- answer route requires `create-evidence-case` because a claim needs durable
  evidence anchoring

Cases must use the existing Watch schema:

- `watch_evidence_cases`
- `watch_evidence_edges`
- `watch_overlay_records`

Case type additions required for real-time tracking:

```text
REALTIME_ENTITY_TRACKING
STREAM_TELEMETRY_VISUAL_MISMATCH
```

Failure code additions required for streaming:

```text
TRACK_IDENTITY_UNCERTAIN
TRACK_FRAGMENTED
STREAM_SEGMENT_EXPIRED
LIVE_OBSERVATION_UNGROUNDED
```

## Brave Search Domain Seeding

Brave Search is used during domain hydration, not as the final evidence answer.

For a movie asset, the domain hydrator should search for:

```text
<movie title> <release year> cast characters
<movie title> full cast character names
<movie title> actor character <candidate name>
```

For Bad Santa, the current Brave lookup returned seed candidates including:

- Billy Bob Thornton -> Willie
- Tony Cox -> Marcus
- Brett Kelly -> The Kid
- Lauren Graham -> Sue
- Bernie Mac -> Gin
- John Ritter -> Bob Chipeska

The domain record shape:

```json
{
  "record_type": "movie_domain_entity",
  "schema_version": "movie_domain.entity.v1",
  "_key": "marcus_bad_santa_2003",
  "asset_uid": "movie_bad_santa_2003_unrated",
  "name": "Marcus",
  "kind": "CHARACTER",
  "actor_name": "Tony Cox",
  "aliases": ["Marcus", "mall-store elf"],
  "source_refs": [
    {
      "source": "brave-search",
      "url": "https://www.imdb.com/title/tt0307987/fullcredits/",
      "retrieved_at": "2026-06-27T15:44:00Z",
      "claim": "Tony Cox is credited as Marcus."
    }
  ],
  "status": "DOMAIN_PRIOR"
}
```

If Brave or another domain source says a character exists but no Watch frame,
clip, transcript, or track supports that character in the segment, the correct
result is a coverage gap or inconclusive case, not a verified scene answer.

## Memory and Vector Persistence

Use memory HTTP boundaries. Do not write raw AQL from Watch.

Schema artifact:

- `watch_track_observations.schema.json`
- `watch_track_observation.bad_santa_marcus.sample.json`

### Arango / Memory Collections

Proposed or existing collections:

- `movie_domain_assets`
- `movie_domain_entities`
- `watch_content`
- `watch_track_observations`
- `watch_evidence_cases`
- `watch_evidence_edges`
- `watch_overlay_records`

### Graph Edges

Required edge predicates:

- `ASSET_HAS_ENTITY`
- `SEGMENT_HAS_TRACK`
- `TRACK_CANDIDATE_ENTITY`
- `OBSERVATION_FROM_FRAME`
- `OBSERVATION_FROM_CLIP`
- `OBSERVATION_HAS_VECTOR`
- `CASE_HAS_OBSERVATION`
- `CASE_GROUNDS_ENTITY`
- `CASE_CORROBORATED_BY_DOMAIN`

### Qdrant / Jina Multimodal Embedding

Qdrant stores embeddings for:

- representative frame crops
- full scene marker frames
- transcript chunks
- SRT/Whisper snippets
- optional short clip embeddings when supported

Arango memory records store only pointers:

```json
{
  "qdrant_collection": "watch_multimodal",
  "point_id": "movie_bad_santa_2003_seg_0007_frame_crop_track_07",
  "embedding_model": "jina-clip-or-current-watch-multimodal-model",
  "modality": "frame_crop",
  "source_hash": "sha256:..."
}
```

This enables recall queries such as:

```text
find all movie segments with the Willie character
find all tracks visually similar to Marcus
find all clips where transcript mentions Santa but visual track is Marcus
```

## Watch Agent Memory Pipeline

The Watch chat status must show the memory pipeline dynamically:

```text
/intent
extract entities
/recall
create evidence case, if needed
/answer | /clarify | /deflect
```

This pipeline belongs in the Watch Agent chat thinking/status UX, not in the
Library ingest panel.

Routing rules:

- `ANSWER`: synthesize from extracted Watch evidence and domain memory.
- `CLARIFY`: ask targeted missing-context question. Do not force a case.
- `DEFLECT`: fail closed and do not enter evidence-case creation.
- `APP_COMMAND`: execute UI command such as isolate, seek, filter, or open case.

## UI Responsibilities

### Video Player

- Render live track overlays.
- Show provisional labels with confidence and status.
- Allow operator to approve, reject, or create case from a label.
- Seek row/table on track or timestamp click.

### Table

- Show segment-bounded evidence rows.
- Keep frame/clip playback available.
- Do not hide source evidence behind summaries.
- Show domain-linked entity markers only when sourced.

### Library

- Show asset and ingest state.
- Collapse ingest pipeline under the asset being ingested.
- Do not show memory thinking pipeline in the Library panel.

### Watch Agent Chat

- Show dynamic memory pipeline status.
- Render entity mentions as light domain markers.
- Create evidence cards only when there is actual evidence.
- Do not treat Brave results as frame evidence.

## First Canary

Asset: Bad Santa 2003.

Canary question:

```text
find all movie segments with Marcus
```

Minimum canary requirements:

1. Brave Search hydrates the movie-domain entity `Marcus -> Tony Cox`.
2. Watch rows expose frames, clips, transcript/SRT/Whisper, and segment ranges.
3. Tracker emits live `track_update` events during playback.
4. Segment-bounded `watch_track_observation` records are prepared for memory.
5. Recall can retrieve Marcus-linked segments by entity id and by text alias.
6. If visual tracking cannot support Marcus in a segment, the answer is
   inconclusive or coverage gap, not fabricated support.

## Completion Evidence Required Later

This contract is not implementation proof. The implementation is not complete
until there is evidence for all of:

- Brave Search seed artifact for one movie.
- Memory upsert receipt for domain entities.
- Tracker event log from playback or fixture video.
- Memory upsert receipt for at least one bounded track observation.
- Qdrant pointer metadata for at least one frame crop or text chunk.
- Recall proof for `find all movie segments with Marcus`.
- UI screenshot showing live/provisional tracking status or a recorded replay.
- Evidence case sample when a mismatch is detected.
