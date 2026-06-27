# Clarify, Then Create Full Architecture And Code Solution

## Objective

Create the scoped `watch-reference-hydration-P0` architecture and implementation-ready solution for Watch. The purpose is to make real-time movie-character tracking work as the test case for the future AO/multi-drone stream system:

- stream ML tracking live,
- automatically hydrate cinema/movie cast and character reference packages before ingest,
- accept source-provided references for drone/ITAR/RTSP/YouTube streams,
- verify track crops/frames against approved references and transcript/context,
- persist bounded observations/cases through `$memory`, Arango metadata, and Qdrant/Jina multimodal embeddings,
- later support `$memory recall` queries such as "find all movie segments with Willie".

## HANDOFF.md

See `HANDOFF.md` in this same creation bundle. Key facts:

- Canopy canary exists for Bad Santa.
- There are 80 YOLO/ByteTrack events, 10 overlay records, 10 crops, and 0 supported identities.
- Brave Search yielded public candidate sources but no approved reference images.
- Qdrant/Arango/memory writes are planned, not proven.

## GOAL.md

See `GOAL.md` in this same creation bundle. Key output must include:

- architecture contract,
- schemas/API contracts,
- state machine,
- lifecycle,
- fail-closed behavior,
- idempotent persistence keys,
- memory/Qdrant/Arango write/read contracts,
- tests/fixtures,
- file-by-file patch plan,
- exact commands,
- rollback/rebuild,
- prompt improvements.

## Rendered Goal Page Or Visual Reference

See `GOAL_PAGE.html` in this same creation bundle. It is a source-derived target model for the P0 slice and should be used to identify missing files, states, schemas, tests, and acceptance gates.

## Current Local Evidence

Generated local artifacts:

- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_yolo_bytetrack/watch_tracker_event_log.bad_santa_marcus.yolo_bytetrack.jsonl`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_yolo_bytetrack/summary.json`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_yolo_overlay_payload/watch_ui_overlay_payload.bad_santa_marcus.json`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_tracking_crops/watch_tracking_crops.bad_santa_marcus.json`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_tracking_crops/watch_tracking_crops.contact_sheet.jpg`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_identity_verification/watch_identity_verification.bad_santa_marcus.json`
- `skills/watch/docs/architecture/generated/bad_santa_character_reference_sources/summary.json`
- `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_identity_references/watch_identity_reference_manifest.bad_santa_marcus.json`

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
```

## Relevant Files And Snippets

Relevant project docs:

- `skills/watch/README.md`
- `skills/watch/docs/PROJECT_KNOWLEDGE.md`
- `skills/watch/docs/architecture/watch_realtime_tracking_execution_plan.md`

Relevant scripts:

- `skills/watch/scripts/extract_tracking_crops.py`
- `skills/watch/scripts/verify_tracking_identity.py`
- `skills/watch/scripts/build_identity_reference_manifest.py`

Important current policy from docs:

- Cinema/movie assets must default to automatic domain/reference hydration before ingest.
- Drone/ITAR/RTSP/YouTube assets should use source-provided manifests/asset registry/channel metadata first.
- Missing source manifest or approved reference package must fail closed.
- Arango stores metadata and Qdrant pointers; raw vectors are not stored in Arango.
- Identity stays inconclusive when only detector labels and domain priors exist.

## Constraints

- Use `$memory` pipeline semantics: `/intent -> extract-entities -> /recall -> create-evidence-case if needed -> answer/clarify/deflect`.
- Memory recall is the official retrieval path; do not bypass it with direct Qdrant or Arango answers.
- Qdrant should hold multimodal/text embeddings; Arango should hold structured metadata and Qdrant pointers.
- Movie-domain public search can provide reference candidates, not scene truth.
- ITAR/drone streams should not default to public web search.
- Detector labels are observations only and cannot promote identity alone.
- Persistence must be idempotent and rebuildable.
- A later UI should show real-time overlays, but this P0 architecture may focus on contracts and scripts first.

## Non-Goals

- Do not redesign the Watch table/chat.
- Do not implement full drone AO command and control.
- Do not make a new bespoke memory system.
- Do not claim live identity proof from current canary artifacts.
- Do not produce a review verdict.

## Required Output

If any material ambiguity remains, return only numbered clarifying questions.

If no material ambiguity remains, return a complete **solution zip bundle**, not inline multi-file prose and not a review.

**If more than one finished file:** one zip + `MANIFEST.json` is mandatory.
**Zip download name:** `watch-reference-hydration-P0-solution.zip` and set `bundle_filename` in the manifest.

The solution must include:

- architecture contract,
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
