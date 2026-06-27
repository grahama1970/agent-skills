# GOAL: Watch Reference Hydration P0

## Primary Question

How should Watch automatically build and use a reference package so real-time ML character/object tracks can be verified, streamed, and persisted into `$memory` without turning public search results or detector labels into unsupported scene truth?

## Scope

Create the architecture and implementation contract for the P0 reference-hydration slice:

1. **Cinema/movie assets** automatically collect movie-domain cast/character reference candidates before ingest/tracking.
2. **Drone/ITAR/RTSP/YouTube assets** accept a source-provided reference manifest or source metadata package and fail closed when it is missing.
3. **Real-time tracker output** streams at a low-rate verification cadence, e.g. 5 FPS, while preserving a continuous track id.
4. **Identity verification** compares track crops/frames against approved reference packages plus segment text/transcript/context.
5. **Memory persistence** stores bounded trace observations, identity evidence, and watch evidence cases through the memory pipeline.
6. **Recall** can later answer requests such as "find all movie segments with Willie" from stored multimodal/text traces.

## Non-Goals

- Do not redesign the Watch table or chat UI.
- Do not claim that YOLO alone identifies a named character.
- Do not infer identity from Brave Search snippets alone.
- Do not implement a full production drone AO command system in this slice.
- Do not write raw vectors into Arango.
- Do not make Qdrant writes without idempotent keys and recall proof.
- Do not treat public web search as authoritative for restricted/ITAR streams.

## Source Of Truth Boundaries

- **Canonical asset source**: video segment, transcript/SRT/Whisper, telemetry or source manifest.
- **Reference package**: domain prior; it helps verify identity but is not scene truth.
- **ML tracker output**: observation proposal; not identity truth.
- **Memory/Qdrant/Arango**: persistence and recall surfaces; not authority for creating unsupported identities.
- **Human approval**: required before ambiguous identity promotion when visual match confidence or provenance is insufficient.

## Required State Machine

The solution should define states like:

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

## Acceptance Gates

P0 is not green until a later local implementation can prove:

1. Movie ingest starts by creating a reference-hydration plan for known cast/characters.
2. Non-movie stream ingest can consume a source-provided reference manifest and fails closed if absent.
3. Track crops are linked to deterministic observation ids and segment ids.
4. Approved references and track observations produce deterministic Qdrant point ids.
5. Arango records store metadata and Qdrant pointers, not raw vectors.
6. Watch evidence cases can anchor `entity_ids` plus `time_range`.
7. A real `$memory recall` query retrieves stored Watch traces by entity and time range.
8. Identity remains `INCONCLUSIVE` when only detector label + web source candidates exist.

## Expected WebGPT Output

If material ambiguity remains, ask numbered clarifying questions only.

If no material ambiguity remains, create an implementation-ready solution bundle for this P0 slice:

- Architecture contract.
- Schemas/API contracts.
- State machine.
- Lifecycle flow.
- Error/fail-closed behavior.
- Idempotent persistence keys.
- Memory/Qdrant/Arango write/read contracts.
- Test fixtures and expected outputs.
- File-by-file patch plan for the Watch skill.
- Exact commands for local sanity checks.
- Rollback/rebuild plan.
- `prompt_improvements` for the next round.

If producing 2+ files, use one solution zip named `watch-reference-hydration-P0-solution.zip` with `MANIFEST.json`.
