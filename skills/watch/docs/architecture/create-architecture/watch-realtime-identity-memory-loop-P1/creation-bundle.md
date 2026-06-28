# Clarify, Then Create Watch Realtime Identity Memory Loop Architecture

## Objective

Create the scoped `watch-realtime-identity-memory-loop-P1` architecture and implementation-ready solution for Watch.

The purpose is to make realtime movie-character tracking work as the test case for the future AO/multi-drone stream system:

- stream ML tracking live while the asset plays,
- use movie-domain cast/character references from Brave Search and curated image candidates before ingest,
- use source-provided manifests for drone/ITAR/RTSP/YouTube assets,
- verify track crops/frames against approved references and segment text/context,
- store trace observations, evidence cases, and retrieval pointers through `$memory`, Arango metadata, and Qdrant/Jina multimodal embeddings,
- support later `$memory recall` queries such as "find all movie segments with Willie".

## HANDOFF.md

See `HANDOFF.md` in this same creation bundle. Key facts:

- Current Watch UI can show library, forensic table, inline clip thumbnails, modal player, and static annotation overlays.
- Current annotation overlays are not realtime tracking proof.
- A Bad Santa canary exists with YOLO/ByteTrack event artifacts and crop artifacts.
- Identity verification currently stays inconclusive, which is correct because approved reference images and embeddings are missing.
- Commit `137948af2` added a row-text materialization receipt plan and was pushed to `origin/main`.

## GOAL.md

See `GOAL.md` in this same creation bundle. Key output must include:

- architecture contract,
- ML tracking runtime plan,
- reference hydration lifecycle,
- state machine,
- schemas/API contracts,
- memory/Qdrant/Arango write/read contracts,
- realtime overlay event contract,
- tests/fixtures,
- file-by-file patch plan,
- exact commands,
- rollback/rebuild,
- prompt improvements.

## Rendered Goal Page Or Visual Reference

See `GOAL_PAGE.html` in this same creation bundle. It is a source-derived target model for the P1 slice and should be used to identify missing files, states, schemas, tests, and acceptance gates.

## Current Local Evidence

Generated local artifacts already exist from prior work:

- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_yolo_bytetrack/watch_tracker_event_log.bad_santa_marcus.yolo_bytetrack.jsonl`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_yolo_bytetrack/summary.json`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_yolo_overlay_payload/watch_ui_overlay_payload.bad_santa_marcus.json`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_tracking_crops/watch_tracking_crops.bad_santa_marcus.json`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_tracking_crops/watch_tracking_crops.contact_sheet.jpg`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_identity_verification/watch_identity_verification.bad_santa_marcus.json`
- `skills/watch/docs/architecture/generated/bad_santa_character_reference_sources/summary.json`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_identity_references/watch_identity_reference_manifest.bad_santa_marcus.json`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_row_text_materialization_receipt_plan/watch_row_text_materialization_receipt_plan.bad_santa_marcus.json`

Command evidence already produced locally:

```text
python3 skills/watch/scripts/extract_tracking_crops.py ...
tracking_crops_ok 10

python3 skills/watch/scripts/verify_tracking_identity.py ...
identity_verification_ok 10
supported_count 0
inconclusive_count 10
failure_codes ['DOMAIN_PRIOR_ONLY', 'NEEDS_HUMAN_REVIEW', 'TRACK_IDENTITY_UNCERTAIN']

python3 skills/watch/scripts/build_identity_reference_manifest.py ...
identity_reference_manifest_ok 1
review_crop_count 10
approved_reference_count 0
reference_source_candidate_count 2

python3 skills/watch/scripts/build_watch_row_text_materialization_receipt_plan.py ...
status BLOCKED_PENDING_SOURCE_REFS
required_channel_count 4
planned_source_read_count 3
blocked_source_ref_count 1
materialized_text_channel_count 0
```

## Relevant Files And Snippets

Relevant project docs:

- `skills/watch/README.md`
- `skills/watch/docs/PROJECT_KNOWLEDGE.md`
- `skills/watch/docs/architecture/watch_realtime_tracking_execution_plan.md`
- `skills/watch/docs/architecture/schemas/watch_row_text_materialization_receipt_plan.schema.json`

Relevant scripts:

- `skills/watch/scripts/watch_reference_hydration.py`
- `skills/watch/scripts/build_watch_row_text_materialization_receipt_plan.py`
- `skills/watch/scripts/extract_tracking_crops.py`
- `skills/watch/scripts/verify_tracking_identity.py`
- `skills/watch/scripts/build_identity_reference_manifest.py`

Important current policy:

- Cinema/movie assets must default to automatic domain/reference hydration before ingest.
- Drone/ITAR/RTSP/YouTube assets should use source-provided manifests/asset registry/channel metadata first.
- Missing source manifest or approved reference package must fail closed.
- Arango stores metadata and Qdrant pointers; raw vectors are not stored in Arango.
- Identity stays inconclusive when only detector labels and domain priors exist.
- `$memory recall` is the official retrieval path for user-facing answers.

## Constraints

- Use `$memory` pipeline semantics: `/intent -> extract-entities -> /recall -> create-evidence-case if needed -> answer/clarify/deflect`.
- Memory recall is the official retrieval path; do not bypass it with direct Qdrant or Arango answers.
- Qdrant should hold multimodal/text embeddings; Arango should hold structured metadata and Qdrant pointers.
- Movie-domain public search can provide reference candidates, not scene truth.
- ITAR/drone streams should not default to public web search.
- Detector labels are observations only and cannot promote identity alone.
- Persistence must be idempotent and rebuildable.
- The chosen ML package plan should include Ultralytics YOLO plus ByteTrack unless WebGPT identifies a better practical default and explains the tradeoff.
- The realtime verification cadence should be bounded, with 5 FPS as the starting target.
- UI redesign is not the task; only specify the realtime overlay event contract needed by the existing modal/player.

## Non-Goals

- Do not redesign the Watch table/chat.
- Do not implement full drone AO command and control.
- Do not make a new bespoke memory system.
- Do not claim live identity proof from current canary artifacts.
- Do not produce a review verdict.
- Do not provide only prose; provide a solution bundle if no clarifying questions are required.

## Required Output

If any material ambiguity remains, return only numbered clarifying questions.

If no material ambiguity remains, return a complete **solution zip bundle**, not inline multi-file prose and not a review.

**If more than one finished file:** one zip + `MANIFEST.json` is mandatory.
**Zip download name:** `watch-realtime-identity-memory-loop-P1-solution.zip` and set `bundle_filename` in the manifest.

The solution must include:

- architecture contract,
- ML tracking package/runtime plan,
- reference hydration lifecycle,
- state machine,
- schemas/API contracts,
- file-by-file implementation as finished files or precise diffs,
- zip bundle manifest with paths and checksums,
- tests/fixtures,
- commands,
- rollback/rebuild steps,
- known gaps,
- `prompt_improvements`: what the project agent should include, remove, clarify, or phrase differently in the next turn so WebGPT can be more useful.

Do not return `PASS`, `NEEDS_CHANGES`, or `BLOCKED`.
Do not leave choices for the project agent when the stated constraints are sufficient for WebGPT to choose.
