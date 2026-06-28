# Handoff Report: Watch Realtime Identity Memory Loop P1

**Timestamp**: 2026-06-28T00:00:00-04:00
**Active Agent**: Codex

## 1. Project Overview

- **Project**: `watch` skill in `agent-skills`
- **Core purpose**: Video memory for agents. Movies are the current test case for a future AO/multi-stream system where live video, transcript/telemetry, entity tracks, and evidence cases persist into memory.
- **Target user job**: Load an asset, ingest frames/segments/transcripts, track entities in real time, verify identity against domain references, and retrieve bounded traces/cases later through `$memory recall`.

## 2. Current State

Implemented or partially implemented local artifacts:

- Watch UI can show a library tab, ingest status, forensic table, inline clip thumbnails, modal video player, and annotation overlays.
- Current modal annotation overlays can visually flag a character such as Willie, but they are not yet realtime tracking updates.
- YOLO/ByteTrack-derived event artifacts exist for a Bad Santa canary.
- Crop extraction exists for one canary segment.
- A fail-closed identity verification report exists and refuses to promote identity without approved references.
- Brave Search result summaries exist for Bad Santa character/cast reference-source candidates.
- A reference manifest exists, but approved reference images and embeddings are not yet proven.
- A row-text materialization receipt plan exists and is pushed in commit `137948af2`.

## 3. Evidence Snapshot

Current repo commit pushed before this bundle:

- Commit: `137948af2 Add Watch row text materialization receipt plan`
- Pushed refs: `origin/main` and `origin/feat/webgpt-no-activate`

Current row-text materialization canary:

- Schema: `watch.row_text_materialization_receipt_plan.v1`
- Status: `BLOCKED_PENDING_SOURCE_REFS`
- Required channel count: `4`
- Planned source read count: `3`
- Blocked source ref count: `1`
- Source ref count: `3`
- Materialized text channel count: `0`
- Blocked channel: `srt_text` lacks source ref.

Current tracking/reference canary:

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

Local verification already run for commit `137948af2`:

```text
python3 -m py_compile skills/watch/scripts/watch_reference_hydration.py skills/watch/scripts/build_watch_row_text_materialization_receipt_plan.py
json_parse_ok 2
pytest -q skills/watch/tests/test_watch_reference_hydration_P0.py
12 passed in 0.21s
python3 scripts/check_mock_evidence_claims.py
OK: checked 300 test file(s); no mock+proof claim violations
```

## 4. What Is Broken Or Missing

- The modal annotation box is still aspiration/static overlay behavior, not a realtime tracked bounding box.
- The ML track is not identity-verified against approved reference-image embeddings.
- Movie ingest does not yet automatically hydrate the cast/character reference package before tracking.
- Brave Search results have not been turned into downloaded, curated, approved, embedded reference images.
- Qdrant/Jina multimodal embeddings and Arango/Qdrant pointers are planned but not written.
- `$memory recall` cannot yet answer "find all movie segments with Willie" from stored trace observations.
- Drone/YouTube/RTSP assets need a source-provided reference manifest path rather than default public web search.
- Watch UI files are dirty from unrelated work and should not be rewritten by this architecture slice.

## 5. Files In Scope For Architecture

- `skills/watch/README.md`
- `skills/watch/docs/PROJECT_KNOWLEDGE.md`
- `skills/watch/docs/architecture/watch_realtime_tracking_execution_plan.md`
- `skills/watch/scripts/watch_reference_hydration.py`
- `skills/watch/scripts/build_watch_row_text_materialization_receipt_plan.py`
- `skills/watch/scripts/extract_tracking_crops.py`
- `skills/watch/scripts/verify_tracking_identity.py`
- `skills/watch/scripts/build_identity_reference_manifest.py`
- Generated evidence under `skills/watch/docs/architecture/generated/`

## 6. Must Not Disturb

- Do not stage or rewrite unrelated dirty Watch UI files.
- Do not treat Brave Search text as scene truth.
- Do not write raw vectors to Arango.
- Do not promote identity from detector labels alone.
- Do not claim Qdrant/memory persistence until a real write and recall proof exists.
- Do not invent a new memory system instead of using `$memory` contracts.

## 7. Next Build Step

Use `$create-architecture` through `$ask webgpt` to produce a scoped architecture and solution package for `watch-realtime-identity-memory-loop-P1`: realtime YOLO/ByteTrack identity tracking, cast/reference hydration before movie ingest, fail-closed identity verification, row-text materialization, and persistence/recall contracts into `$memory`, Qdrant, and Arango.
