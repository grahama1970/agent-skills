# GOAL: Watch Realtime Identity Memory Loop P1

## Primary Question

How should Watch turn movie-character tracking into a real-time, memory-backed identity loop that can later generalize to many drones in an AO?

Movies are the test case. The architecture must support a path where a video segment is tracked live, character/entity identity is verified against approved domain references, and bounded trace evidence is persisted for later `$memory recall` queries such as "find all movie segments with Willie".

## Scope

Create the architecture and implementation contract for the P1 realtime identity loop:

1. **Pre-ingest movie-domain hydration**: collect cast, character, and approved reference-image candidates before movie ingest starts.
2. **Non-movie reference path**: require source-provided reference manifests for drone, ITAR, RTSP, and YouTube assets when public search is inappropriate or insufficient.
3. **Realtime ML tracking**: use an explicit detector/tracker plan, with Ultralytics YOLO plus ByteTrack as the practical default, producing low-latency track events while the movie/stream plays.
4. **Verification cadence**: sample at a bounded cadence such as 5 FPS for identity verification and embedding, while preserving continuous track ids.
5. **Multimodal memory loop**: store track crops, frame refs, row text, transcripts, source refs, and embeddings through `$memory` contracts backed by Qdrant/Jina multimodal embeddings plus Arango graph metadata/pointers.
6. **Entity and evidence cases**: create `watch_evidence_cases` only when the evidence supports a bounded case anchor by `entity_ids` plus `time_range`.
7. **Chat recall**: route user requests through `/intent -> extract-entities -> /recall -> create-evidence-case if necessary -> answer/clarify/deflect`.

## Non-Goals

- Do not redesign the Watch table or chat UI in this slice.
- Do not claim current static annotation boxes are realtime tracking proof.
- Do not infer named character identity from YOLO alone.
- Do not infer scene truth from Brave Search or public web snippets.
- Do not require public web search for restricted drone/ITAR streams.
- Do not write raw vectors into Arango.
- Do not claim memory/Qdrant persistence without a real write and recall proof.
- Do not implement a complete multi-drone AO command system in this slice.

## Source Of Truth Boundaries

- **Video frames and segments** are source evidence.
- **SRT/Whisper/telemetry/source manifests** are aligned evidence channels, not automatically correct.
- **Brave Search/cast data** are movie-domain reference candidates, not scene truth.
- **YOLO/ByteTrack detections** are observation proposals, not named identity truth.
- **Qdrant/Jina embeddings** support similarity search and recall, not authority.
- **Arango** stores graph metadata and pointers, not raw vectors.
- **Human approval** is required before ambiguous identity promotion.

## Required State Machine

The solution should define transitions for at least:

- `ASSET_REGISTERED`
- `REFERENCE_DISCOVERY_PLANNED`
- `REFERENCE_CANDIDATES_COLLECTED`
- `REFERENCE_IMAGES_DOWNLOADED`
- `REFERENCE_IMAGES_PENDING_APPROVAL`
- `REFERENCE_EMBEDDINGS_READY`
- `INGEST_READY`
- `TRACK_STREAM_ACTIVE`
- `TRACK_OBSERVATION_CAPTURED`
- `IDENTITY_CANDIDATE`
- `IDENTITY_SUPPORTED`
- `IDENTITY_INCONCLUSIVE`
- `IDENTITY_REFUTED`
- `ROW_TEXT_MATERIALIZED`
- `MEMORY_WRITE_PLANNED`
- `MEMORY_PERSISTED`
- `RECALL_VERIFIED`
- `CASE_ANCHOR_CREATED`

## Acceptance Gates

P1 is not green until a later local implementation can prove:

1. Movie ingest creates a reference-hydration plan before ingest/tracking.
2. At least one approved reference-image fixture can be embedded with deterministic Qdrant ids.
3. A YOLO/ByteTrack event stream fixture produces deterministic track observations at the selected verification cadence.
4. Track observations link to segment ids, frame ids, crop artifact refs, and row-text refs.
5. Row text materialization reads source refs instead of copying visible UI text.
6. The identity verifier stays `INCONCLUSIVE` when only detector labels and public search candidates exist.
7. Arango records store metadata and Qdrant point ids, not raw vectors.
8. A real `$memory recall` query can retrieve Watch trace evidence by entity and time range.
9. `watch_evidence_cases` are only created when the case anchor has both entity evidence and time-range evidence.
10. The modal/overlay realtime UI has a data contract for live track updates, even if UI polish is out of scope.

## Expected WebGPT Output

If material ambiguity remains, ask numbered clarifying questions only.

If no material ambiguity remains, create an implementation-ready solution bundle for this P1 slice:

- Architecture contract.
- ML tracking package and runtime plan.
- Reference hydration lifecycle.
- State machine.
- Schemas/API contracts.
- Memory/Qdrant/Arango write/read contracts.
- `watch_evidence_cases` contract.
- Realtime overlay event contract.
- Test fixtures and expected outputs.
- File-by-file patch plan for the Watch skill.
- Exact commands for local sanity checks.
- Rollback/rebuild plan.
- `prompt_improvements` for the next round.

If producing 2+ files, use one solution zip named `watch-realtime-identity-memory-loop-P1-solution.zip` with `MANIFEST.json`.
