# Watch Real-Time Character Tracking Contract Inspection

Status: REVISE
Inspected: 2026-06-27
Artifact: `skills/watch/docs/architecture/watch_realtime_character_tracking_contract.md`

## Inspection Method

Manual contract inspection against the active objective:

> Develop a Watch architecture plan for real-time movie-character tracking as a
> test case for multi-drone AO management: stream ML tracking live, seed/verify
> actors and characters with Brave Search domain data, and persist bounded
> traces/cases into memory/Qdrant/graph without treating web data as scene truth.

## Coverage

| Requirement | Covered by artifact | Evidence |
| --- | --- | --- |
| Real-time stream of ML tracking | Yes | `Live ML Pipeline`, `track_update` event |
| Movies as test case for AO/drone management | Yes | `Purpose`, `Stream Model` |
| Brave Search actor/character domain seeding | Yes | `Brave Search Domain Seeding` |
| Brave does not override scene truth | Yes | `Non-Negotiable Boundaries`, domain seeding notes |
| Bounded memory persistence | Yes | `Verification Pass`, `Memory and Vector Persistence` |
| Qdrant/Jina multimodal role | Yes | `Qdrant / Jina Multimodal Embedding` |
| Arango graph edge role | Yes | `Graph Edges` |
| Existing Watch case schema alignment | Partial | Uses existing collections and proposes additions |
| Streamed content eventually | Yes | `EvidenceStream`, stream types |
| Dynamic memory pipeline belongs in chat UX | Yes | `Watch Agent Memory Pipeline` |

## Defects

1. `watch_evidence_cases.schema.json` now includes the proposed
   `REALTIME_ENTITY_TRACKING` and `STREAM_TELEMETRY_VISUAL_MISMATCH` case
   types, but no live case has been written.
2. `watch_evidence_cases.schema.json` now includes streaming-specific failure
   codes: `TRACK_IDENTITY_UNCERTAIN`, `TRACK_FRAGMENTED`,
   `STREAM_SEGMENT_EXPIRED`, `LIVE_OBSERVATION_UNGROUNDED`.
3. `watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json`
   defines the first dry-run memory/Qdrant/graph write plan, but it has not
   been posted to memory.
4. `watch_track_observations.schema.json` now exists and the offline dry-run
   payload builder consumes tracker events against that schema.
5. No live memory upsert/recall proof exists yet.
6. `watch_tracker_event_log.bad_santa_marcus.fixture.jsonl` now exists as a
   deterministic track-event fixture.
7. `docs/architecture/generated/bad_santa_marcus_0248_upsert_payloads/`
   contains concrete dry-run `/upsert` request bodies generated from the
   accepted manifest and tracker fixture.
8. `scripts/build_realtime_tracking_event_log.py` now emits frame-backed
   schema-valid live-track JSONL from the manifest's representative frame, but
   it is deterministic harness output, not YOLO/ByteTrack runtime output.
9. `scripts/track_yolo_bytetrack.py` now maps Ultralytics YOLO + ByteTrack
   results into the Watch live-track JSONL contract, but local inspection has
   only exercised fake result objects because `ultralytics` is not installed.

## Status

REVISE

The artifact is directionally aligned and source-aware, but it remains a
contract/proof-ladder artifact until live memory write/recall and live playback
tracker evidence exist.

## Next Legal Move

Install the Watch `tracking` extra in a controlled runtime, run
`track_yolo_bytetrack.py` against the manifest clip, and compare its emitted
JSONL with the deterministic frame harness. Live memory writes remain gated on
human approval plus recall-proof queries.
