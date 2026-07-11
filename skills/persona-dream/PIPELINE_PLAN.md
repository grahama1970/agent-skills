# Persona-Dream Storyboard-First Kling Plan

Date: 2026-06-12

Source assessment:

```text
skills/persona-dream/PIPELINE_ASSESSMENT.md
```

WebGPT review run:

```text
/mnt/storage12tb/skills/ask/outputs/persona-dream-pipeline-plan/persona-dream-pipeline-plan-20260612-r4
```

WebGPT verdict:

```text
NEEDS_CHANGES
```

## Plan Objective

Make `persona-dream` a storyboard-first, receipt-backed video pipeline that can
take a seed story through reference sheets, storyboard board, Kling provider
packet, live provider execution, and visual review without bespoke scripts or
ambiguous completion claims.

The near-term goal is not a live Kling video. The near-term goal is a validated
dry-run fixture that proves the story, visual identity, reference-sheet,
storyboard-board, and provider-packet contracts before any paid call.

Default entrypoint:

```text
persona/project memory + recent project knowledge + optional Brave context
-> idea_contract.json
-> $create-story
```

A human or project agent can pass a specific idea, but that is an override mode
recorded in `idea_contract.json`. The reusable `$persona-dream` behavior is
autonomous dreaming from persona memories mixed with project knowledge in
`$memory`; it should not require the human to hand-author the premise.

## Status Vocabulary

Use only these status labels in receipts and reports:

```text
NOT_STARTED
BLOCKED
GENERATED_UNREVIEWED
FAILED_AUTOMATED_CHECK
FAILED_MANUAL_REVIEW
ACCEPTED_AUTOMATED
ACCEPTED_MANUAL
PROVIDER_PACKET_ACCEPTED
LIVE_RENDER_SUBMITTED
LIVE_RENDER_ACCEPTED
SUPERSEDED
```

Do not use final/complete/ready/fixed language unless the current scope's
required receipts exist and pass.

## Skill Boundaries

### `$persona-dream`

Owns:

- Autonomous idea synthesis before story writing.
- Persona memory recall.
- Project-knowledge recall from `$memory`.
- Recent project activity/context intake when available.
- Optional `$brave-search` context for relevant events or canon-sensitive
  grounding.
- `idea_contract.json`.
- `$dogpile` is not the default persona-dream search lane. Escalate to it only
  when the idea requires deep multi-source research beyond raw Brave receipts.

Does not own:

- Turning the accepted idea into a full story; that routes to `$create-story`.
- Visual reference research after entities exist; that routes to
  `$casting-agent`.

Codebase/project-activity questions:

```text
/recall q="<natural-language project question>" scope=<project>
/recall q="<activity question>" collections=["project_activity"]
/recall q="<symbol question>" collections=["code_symbols"]
```

Expected activity metadata should include `meta.recall_profile` of
`temporal_project_state` and `meta.recall_profile_source` of
`deterministic_project_activity` when memory has the needed activity records.
`/recall` does not inspect live git or the filesystem; if activity is missing,
run the appropriate ingestion workflow before using code activity as dream
source material.

Required `idea_contract.json` fields:

```text
schema
artifact_id
status
source_mode
idea
inputs_considered
codebase_question_protocol
selection_policy
created_at
```

Allowed `source_mode` values:

```text
autonomous_memory_project_synthesis
human_supplied_seed
project_agent_supplied_seed
```

### `$create-story`

Owns:

- Story expansion from seed.
- `story_contract.md`
- `story_contract.json`
- `timed_beats.json`
- Dialogue and scene beat text.

Does not own:

- Visual reference research.
- Contact sheets.
- Kling provider requests.

### `$entity-extractor` or `$casting-agent extract`

Owns:

- Convert accepted story into `story_visual_package.json`.
- Key all characters, creatures, scenery, props, and effects.
- Validate required descriptions and optional reference paths.

Decision:

- Start as a `$casting-agent` command if implementation is small.
- Split into `$entity-extractor` only if multiple pipelines need it.

### `$casting-agent`

Owns:

- `casting_contract.json`
- `chosen_reference_inputs.json`
- `contact_sheet_work_order.json`
- Reference sufficiency decisions.
- Brave Search fallback for canon-sensitive missing references.
- Retry decisions after contact-sheet visual failures.

Reference priority:

```text
1. Human/project-agent provided image paths
2. Accepted memory/Qdrant visual assets
3. Project-local artifacts
4. Brave Search receipts
5. Provisional generated placeholders
```

Canon-sensitive reference sufficiency:

- At least one accepted human/provided/memory reference, or
- At least three Brave image/web candidates with source URL and dimensions, or
- A blocked receipt explaining insufficient reference evidence.

For each canon-sensitive entity, the casting contract must propagate:

```text
required_visual_anchors
must_not_include
source_urls
reference_image_paths
prompt_terms_required_downstream
```

### `$contact-sheet`

Owns:

- Reference-sheet generation for characters, creatures, scenery, and props.
- Provider element image sets.
- `layout_validation.json`
- Image prompt receipts and generated image receipts.

Does not own:

- Storyboard board generation.
- Kling provider submission.

Required behavior:

- Preserve aspect ratio by default.
- Record raw image dimensions.
- Record placed-cell dimensions.
- Reject nonuniform scaling unless explicitly requested.
- Human-facing output is a sheet/grid; card galleries are debug-only.

### `$create-storyboard`

Owns:

- `storyboard_prompt.md`
- `storyboard_board.png`
- `storyboard_board_receipt.json`
- Storyboard board validation.

Required new mode:

```bash
./run.sh board \
  --story-contract <story_contract.json> \
  --timed-beats <timed_beats.json> \
  --references <accepted_reference_manifest.json> \
  --out-dir <dir>
```

Automated assertions:

- Board image is 16:9 within tolerance.
- Expected panel count is declared.
- Panel labels/timing/captions are present or manual review marks failure.
- Beat coverage is mapped from timed beats to panel ids.

### `$provider-packet`

Owns:

- `final_kling_prompt.md`
- `provider_request_dry_run.json`
- `referenced_artifacts.lock.json`
- `readiness_receipt.json`

This is a required first-class boundary. The Kling runner should only consume a
validated provider packet.

Dry-run fail-closed checks:

- All referenced paths exist.
- Upstream receipts are accepted, not failed or unreviewed.
- Dialogue and duration exist for speaking shots.
- `paid_call_performed` is false.
- Input artifact hashes are recorded.
- Provider/model/version are declared.

### `$kling-video`

Owns live provider execution only after `$provider-packet` acceptance.

Required live artifacts:

```text
paid_call_approval_receipt.json
upload_receipts.json
provider_queue_events.jsonl
provider_response.json
download_receipt.json
output.mp4
ffprobe.json
frame_sheet.jpg
manual_video_review_receipt.json
```

Live-call guard:

- Explicit human approval receipt.
- Estimated cost/credit budget.
- Provider/model/version.
- Input artifact hashes.
- Idempotency key.
- Retry budget.
- A new approval receipt for paid retries unless pre-authorized.

### `$review-page`

Owns display of existing artifacts only.

Rules:

- No dashboard theater.
- No implied operational truth from missing artifacts.
- Must show actual storyboard, sheets, frame sheet, video, and receipts.
- A review page cannot substitute for missing upstream receipts.

## Required Worked Fixture

The pipeline assessment defines the canonical worked fixture:

```text
skills/persona-dream/PIPELINE_ASSESSMENT.md
section: "Worked Example: Horus/Embry Storyboard-First Dry-Run Fixture"
```

That fixture is a target trace, not proof that artifacts exist. It must become
both documentation and a regression-test target.

Implementation tasks should preserve the fixture's division of labor:

| Stage | Owner | Allowed status before downstream consumption |
| --- | --- | --- |
| Idea synthesis | `$persona-dream` | `ACCEPTED_AUTOMATED` or `BLOCKED` |
| Story contract | `$create-story` | `ACCEPTED_AUTOMATED` or `ACCEPTED_MANUAL` |
| Entity extraction | `$casting-agent extract` | `ACCEPTED_AUTOMATED` |
| Casting/reference research | `$casting-agent` | `ACCEPTED_MANUAL` |
| Reference sheets | `$contact-sheet` + `$create-image` / `$scillm` | `ACCEPTED_MANUAL` |
| Storyboard board | `$create-storyboard` + `$create-image` / `$scillm` | `ACCEPTED_MANUAL` |
| Provider packet | `$provider-packet` | `PROVIDER_PACKET_ACCEPTED` |
| Live provider execution | `$kling-video` | `LIVE_RENDER_ACCEPTED` after explicit approval |
| Review display | `$review-page` | Display-only acceptance; no upstream claims |

No stage may consume a failed, superseded, or generated-unreviewed upstream
artifact unless the consuming stage is explicitly a diagnostic/debug stage.

## Artifact Schemas To Add

Add or formalize schemas for:

```text
idea_contract.schema.json
story_contract.schema.json
timed_beats.schema.json
story_visual_package.schema.json
casting_contract.schema.json
chosen_reference_inputs.schema.json
contact_sheet_work_order.schema.json
layout_validation.schema.json
storyboard_board_receipt.schema.json
provider_request_dry_run.schema.json
readiness_receipt.schema.json
paid_call_approval_receipt.schema.json
live_render_receipt.schema.json
manual_review_receipt.schema.json
```

Each schema-backed artifact must include:

```text
schema
artifact_id
status
created_at
inputs
outputs
checks
failure_reasons
upstream_artifact_hashes_or_paths
```

## Rollback And Retry Model

All stage outputs are immutable once written.

When a stage fails:

- Write a failed receipt.
- Mark downstream artifacts `SUPERSEDED` if they consumed the failed artifact.
- Retry only from the nearest valid upstream accepted checkpoint.
- Keep previous failed artifacts for diagnosis.

Default retry budgets:

```text
casting reference search: 3 rounds
image generation per entity: 2 rounds
layout/render repair: 2 rounds
storyboard board generation: 2 rounds
provider dry-run packet repair: 2 rounds
live paid provider retry: 0 unless explicitly approved
```

Retryable failures:

- Missing or low-quality references.
- Prompt missing required anchors.
- Image layout distortion.
- Missing provider packet fields.
- Missing referenced paths.

Non-retryable without human approval:

- Paid provider submission.
- Conflicting user intent.
- Copyright/legal constraint change.
- Missing source authority for canon identity.

## Acceptance Gates

### Gate 0: Idea Synthesis

Required artifact:

- `idea_contract.json`

Automated checks:

- JSON schema passes.
- `source_mode` is declared.
- Chosen idea text exists.
- `inputs_considered` records either persona/project memory sources or an
  explicit supplied seed.
- Autonomous mode includes persona memory and project-knowledge recall before
  story generation.
- Codebase-grounded autonomous mode records `/recall` questions, `scope`,
  optional `project_activity` / `code_symbols` collections, source refs, and
  recall profile metadata when returned.
- Missing project activity memory blocks the codebase-grounded idea path until
  ingestion populates memory.
- Brave Search context is optional, but when used it has a receipt.

Status on pass:

```text
ACCEPTED_AUTOMATED
```

Status when no source-linked idea can be formed:

```text
BLOCKED
```

### Gate 1: Story

Required artifacts:

- `idea_contract.json`
- `story_contract.md`
- `story_contract.json`
- `timed_beats.json`

Automated checks:

- JSON schema passes.
- Seed idea is preserved.
- Timed beats sum to target duration or declare variance.
- Speaking characters are identified.

Status on pass:

```text
ACCEPTED_AUTOMATED
```

Manual review may promote to:

```text
ACCEPTED_MANUAL
```

### Gate 2: Entity Extraction

Required artifact:

- `story_visual_package.json`

Automated checks:

- JSON schema passes.
- Characters, creatures, scenery, and props are keyed.
- Required descriptions exist.
- Provided image paths exist when present.

### Gate 3: Casting

Required artifacts:

- `casting_contract.json`
- `chosen_reference_inputs.json`
- `contact_sheet_work_order.json`

Automated checks:

- Canon-sensitive entities have sufficient references or blocked receipt.
- Required visual anchors exist.
- `must_not_include` constraints exist.
- Downstream prompt terms are declared.

High-risk entities for first fixture:

```text
Horus Lupercal
Warhammer 40,000 Tyranids
Embry
void world patio
tea table / umbrella / SPARTA laptop
```

### Gate 4: Reference Sheets

Required artifacts:

- Reference sheet PNGs.
- Separate provider images.
- `layout_validation.json`
- Prompt and image receipts.
- Manual visual review receipt.

Automated checks:

- Images exist.
- Raw dimensions recorded.
- Placed-cell dimensions recorded.
- Nonuniform scaling is rejected.
- Minimum side >= 300 px.
- File size <= provider limit.
- Provider image count per Element is 2-4 unless exception recorded.

Manual checks:

- Identity matches casting contract.
- No genericized Horus/Tyranids.
- No visible stretching.
- Main/front/hero image is first.

### Gate 5: Storyboard Board

Required artifacts:

- `storyboard_prompt.md`
- `storyboard_board.png`
- `storyboard_board_receipt.json`
- Manual storyboard review receipt.

Automated checks:

- 16:9 image ratio within tolerance.
- Expected panel count declared.
- Beat-to-panel mapping exists.
- Captions/timings are present or manual review fails.

Manual checks:

- Story matches Horus/Embry patio seed.
- Tyranids appear as background activity.
- SPARTA Explorer discussion is represented.

### Gate 6: Provider Packet Dry Run

Required artifacts:

- `final_kling_prompt.md`
- `provider_request_dry_run.json`
- `referenced_artifacts.lock.json`
- `readiness_receipt.json`

Automated checks:

- All references exist.
- Upstream artifacts are accepted.
- Hash/path lock is present.
- Dialogue/duration exists for speaking shots.
- Provider/model/version declared.
- `paid_call_performed: false`.

Status on pass:

```text
PROVIDER_PACKET_ACCEPTED
```

### Gate 7: Live Kling Render

Required artifacts:

- `paid_call_approval_receipt.json`
- `upload_receipts.json`
- `provider_queue_events.jsonl`
- `provider_response.json`
- `download_receipt.json`
- `output.mp4`
- `ffprobe.json`
- `frame_sheet.jpg`
- `manual_video_review_receipt.json`

Automated checks:

- Approval receipt exists.
- Input hashes match dry-run packet.
- MP4 duration matches expected tolerance.
- Frame sheet generated from the MP4.

Manual checks:

- Horus identity preserved.
- Embry identity preserved.
- Tyranids are 40k-grounded background creatures.
- Lip sync and quality acceptable.
- No artifact contradicts accepted story.

Status on pass:

```text
LIVE_RENDER_ACCEPTED
```

## Regression Fixtures

Add negative fixtures for:

- Stretched image in a contact/reference sheet.
- Missing `storyboard_board.png`.
- Missing Brave/provided-reference provenance for Horus.
- Genericized Horus prompt.
- Genericized Tyranid prompt.
- Missing dialogue/duration for speaking shot.
- Nonexistent referenced image path in provider packet.
- Dry-run receipt claimed as video proof.
- Review-page-only completion.
- Paid call attempted without approval receipt.

## First Implementation Slice

Do not attempt live Kling in this slice.

Target fixture:

```text
Horus and Embry have tea under a patio umbrella on a Warhammer 40k void world
while Tyranids run/play in the background and they discuss SPARTA Explorer.
```

Required outputs:

```text
story_contract.json
timed_beats.json
story_visual_package.json
casting_contract.json
chosen_reference_inputs.json
contact_sheet_work_order.json
horus_reference_sheet.png
tyranid_environment_reference_sheet.png
layout_validation.json
storyboard_prompt.md
storyboard_board.png
storyboard_board_receipt.json
final_kling_prompt.md
provider_request_dry_run.json
referenced_artifacts.lock.json
readiness_receipt.json
```

Minimum proof before moving to live provider:

- Schema validation passes.
- Layout validation rejects no accepted sheet.
- Manual review receipts accept Horus, Tyranids, and storyboard board.
- Provider packet dry-run status is `PROVIDER_PACKET_ACCEPTED`.

## Immediate Engineering Tasks

1. Add schema directory and validators for the first-slice artifacts.
2. Add `$casting-agent` command for `story_visual_package.json` intake and
   reference sufficiency receipts.
3. Add `$contact-sheet` layout validation receipt with raw/placed dimensions and
   nonuniform scaling detection.
4. Add `$create-storyboard board` mode or a minimal script behind that command.
5. Add `$provider-packet` as a new skill or command with dry-run readiness
   checks.
6. Add negative fixtures for stretched images, missing storyboard, and generic
   Horus/Tyranids.
7. Build the Horus/Embry dry-run fixture and review it visually before any
   provider call.

## Open Design Decisions

1. Should entity extraction live inside `$casting-agent` initially, or be split
   into `$entity-extractor` immediately?
2. Should `$provider-packet` be a new skill, or a `persona-dream` subcommand
   promoted after the first fixture?
3. Should `$kling-video` be a new skill now, or wait until the dry-run packet
   contract is stable?
4. What exact human approval receipt format should authorize live paid Kling
   calls?

## Current Recommended Decision

Start with:

```text
$casting-agent extract
$provider-packet as a new narrow skill
$kling-video deferred until provider-packet dry-run is stable
```

This keeps the next slice focused on deterministic contracts and the
storyboard-first artifact path, which is where the current workflow failed.
