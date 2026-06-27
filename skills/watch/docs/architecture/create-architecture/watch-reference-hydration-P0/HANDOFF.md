# Handoff Report: Watch Reference Hydration P0

**Timestamp**: 2026-06-27T20:10:00-04:00
**Active Agent**: Codex

## 1. Project Overview

- **Project**: `watch` skill in `agent-skills`
- **Core purpose**: Video memory for agents. Movies are the current test case for a broader AO/multi-stream system where streamed video, transcript/telemetry, entity tracks, and cases persist into memory.
- **Target user job**: Load an asset, ingest frames/segments/transcripts, track entities in real time, verify identity against domain references, and persist bounded traces/cases for later `$memory recall`.

## 2. Current State

Implemented or partially implemented local artifacts:

- Watch UI can show an asset library, ingest status, forensic table, inline clip thumbnails, a modal video player, and static annotation overlays.
- YOLO/ByteTrack-derived event artifacts exist for the Bad Santa canary.
- Crop extraction exists for a single canary segment.
- A fail-closed identity verification report exists and currently refuses to promote identity.
- Brave Search web result summaries exist for Bad Santa character/cast reference-source candidates.
- A reference manifest exists, but it is still `PLANNED_NOT_WRITTEN` for Qdrant and has `approved_reference_count: 0`.

## 3. Evidence Snapshot

Current canary asset:

- Asset: `Bad.Santa.Unrated.2003.BRRip.XvidHD...`
- Segment focus: `02:48`, visually Marcus/Tony Cox; source track label is not trusted by itself.
- Event summary: 80 YOLO/ByteTrack events previously generated.
- Overlay records: 10 records for the `02:48` canary.
- Crops: 10 PNG crops plus contact sheet.
- Identity verification: 10 inconclusive, 0 supported.
- Failure codes: `DOMAIN_PRIOR_ONLY`, `NEEDS_HUMAN_REVIEW`, `TRACK_IDENTITY_UNCERTAIN`.
- Brave queries: 3.
- Raw Brave web results: 15.
- Marcus-linked query groups: 2.
- Marcus candidate URLs: 10.
- Approved reference images: 0.
- Qdrant writes: none; planned pointers only.

## 4. What Is Broken Or Missing

- Character annotation boxes in the modal are currently static overlays, not real-time tracking updates.
- The ML track is not yet identity-verified against a reference-image pool.
- Movies do not yet auto-hydrate a cast/character reference package before ingest.
- Brave Search results are candidate source links only; no reference images have been downloaded, curated, embedded, or approved.
- Qdrant/Jina multimodal embeddings and Arango/Qdrant pointers are planned but not written.
- `$memory recall` cannot yet answer "find all movie segments with Willie" from stored track traces.
- Drone/YouTube/RTSP assets need a separate source-provided reference manifest path rather than default public web search.

## 5. Files In Scope

- `skills/watch/README.md`
- `skills/watch/docs/PROJECT_KNOWLEDGE.md`
- `skills/watch/docs/architecture/watch_realtime_tracking_execution_plan.md`
- `skills/watch/scripts/extract_tracking_crops.py`
- `skills/watch/scripts/verify_tracking_identity.py`
- `skills/watch/scripts/build_identity_reference_manifest.py`
- Generated evidence under `skills/watch/docs/architecture/generated/`

## 6. Must Not Disturb

- Do not stage or rewrite unrelated dirty UI files in `skills/watch/ui/`.
- Do not treat Brave Search text as scene truth.
- Do not write raw vectors to Arango.
- Do not promote identity from detector labels alone.
- Do not claim Qdrant/memory persistence until a real write and recall proof exists.

## 7. Next Build Step

Use `$create-architecture` through `$ask webgpt` to produce a scoped architecture and solution package for `watch-reference-hydration-P0`: pre-ingest reference hydration for movies, reference manifest handling for drone/stream assets, fail-closed identity promotion, and persistence contracts into `$memory`/Qdrant/Arango.
