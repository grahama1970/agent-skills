# WebGPT Create-Architecture Request: watch-reference-hydration-P0

This is a $create-architecture creation request. Clarify first if materially ambiguous; otherwise create the scoped solution zip.

## creation-bundle.md

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


## HANDOFF.md

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


## GOAL.md

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


## GOAL_PAGE.html

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Watch Reference Hydration P0</title>
  <style>
    body { margin: 0; background: #0b0f14; color: #d8e2ef; font: 14px/1.5 Inter, system-ui, sans-serif; }
    main { max-width: 1180px; margin: 0 auto; padding: 32px; }
    h1, h2 { letter-spacing: .06em; text-transform: uppercase; }
    h1 { color: #03dac6; font-size: 24px; }
    h2 { color: #60a5fa; font-size: 16px; margin-top: 28px; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    .card { border: 1px solid rgba(255,255,255,.12); border-radius: 8px; padding: 14px; background: rgba(255,255,255,.035); }
    .missing { border-color: rgba(255,179,0,.45); }
    .partial { border-color: rgba(96,165,250,.45); }
    .fail { border-color: rgba(207,102,121,.45); }
    code { color: #ffd166; }
    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    th, td { border-bottom: 1px solid rgba(255,255,255,.09); padding: 8px; text-align: left; vertical-align: top; }
    th { color: #93c5fd; text-transform: uppercase; font-size: 11px; letter-spacing: .12em; }
    .flow { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; }
    .flow div { border: 1px solid rgba(3,218,198,.28); border-radius: 6px; padding: 10px; min-height: 80px; background: rgba(3,218,198,.04); }
  </style>
</head>
<body>
<main>
  <h1>Watch Reference Hydration P0</h1>
  <p>Target model for WebGPT creation: make character/object identity verification a fail-closed pipeline that joins movie-domain references, real-time ML tracks, multimodal embeddings, graph metadata, and `$memory recall`.</p>

  <h2>Master Flow</h2>
  <section class="flow">
    <div><strong>1. Asset</strong><br>Cinema, drone, RTSP, YouTube.</div>
    <div><strong>2. Reference</strong><br>Auto-hydrate movie cast refs or require source manifest.</div>
    <div><strong>3. Track</strong><br>YOLO/ByteTrack stream observations and crops.</div>
    <div><strong>4. Verify</strong><br>Compare crop, frame, text, transcript, reference package.</div>
    <div><strong>5. Persist</strong><br>Memory records, Arango metadata, Qdrant pointers.</div>
    <div><strong>6. Recall</strong><br>Find all segments with entity traces and case anchors.</div>
  </section>

  <h2>Current Evidence</h2>
  <table>
    <tr><th>Artifact</th><th>Current Count / State</th><th>Meaning</th></tr>
    <tr><td>YOLO/ByteTrack events</td><td>80</td><td>Tracking exists for one canary, but identity is not proven.</td></tr>
    <tr><td>Overlay records</td><td>10</td><td>Static UI annotation payload exists.</td></tr>
    <tr><td>Track crops</td><td>10 PNG crops + contact sheet</td><td>Visual material exists for reference comparison.</td></tr>
    <tr><td>Identity verification</td><td>0 supported / 10 inconclusive</td><td>Fail-closed behavior is working for the canary.</td></tr>
    <tr><td>Brave source candidates</td><td>3 queries / 15 raw results</td><td>Domain candidates exist; no approved image refs yet.</td></tr>
    <tr><td>Qdrant writes</td><td>0</td><td>Only planned pointer ids exist.</td></tr>
  </table>

  <h2>Capability Gaps</h2>
  <section class="grid">
    <div class="card missing"><strong>Movie reference hydration</strong><br>Missing default pre-ingest cast/character reference package generation.</div>
    <div class="card missing"><strong>Reference image approval</strong><br>Missing automated/manual approval boundary and local cache contract.</div>
    <div class="card missing"><strong>Qdrant/Jina embeddings</strong><br>Missing idempotent point creation and recall proof.</div>
    <div class="card partial"><strong>Tracker crop extraction</strong><br>Partial; canary crops exist, but no streaming verification loop.</div>
    <div class="card fail"><strong>Identity promotion</strong><br>Currently fails closed, as intended, because no reference proof exists.</div>
    <div class="card missing"><strong>Memory recall</strong><br>Missing stored traces that answer entity/time queries.</div>
  </section>

  <h2>Required Fail-Closed Rule</h2>
  <p>Detector labels, Brave snippets, and movie-domain priors are not enough to mark a row as <code>IDENTITY_SUPPORTED</code>. A supported identity needs a bounded observation, an approved reference package, a comparison score/evidence record, and persistence that can be recalled.</p>
</main>
</body>
</html>

```
