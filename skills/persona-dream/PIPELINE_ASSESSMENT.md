# Persona-Dream Pipeline Assessment

Date: 2026-06-12

## Purpose

This assessment resets the `persona-dream` video workflow after user-visible
failures in the Horus/Embry contact-sheet review. The immediate goal is not to
claim the current artifacts are acceptable. The goal is to define the skills and
subagents that should own each stage from `$create-story` through a Kling video
receipt, then send this assessment to `$ask webgpt` for plan review.

## Current Problem

The recent Horus/Embry run produced useful backend artifacts, but the primary
human-facing artifact drifted into a card-gallery/provider-matrix workflow. The
user showed screenshots where images were stretched or framed incorrectly, and
the artifact did not match the intended storyboard-first video workflow.

The prior completion language is invalidated by those screenshots. The current
state is `NEEDS_REASSESSMENT`, not accepted.

## Source Evidence

### User Seed

The accepted seed is:

```text
Horus and Embry have tea under a patio umbrella on a Warhammer 40k void world
while Tyranids play or run in the background, and Horus and Embry discuss
working on SPARTA Explorer.
```

Important user constraints:

- Horus must be Horus Lupercal, Warmaster, from Warhammer 40,000.
- Tyranids must be Warhammer 40,000 Tyranids, not generic alien wildlife.
- Brave Search should ground canon-sensitive visual entities before image
  prompts are written.
- Human-provided reference images should be accepted as higher-priority
  references than Brave Search.
- The pipeline should produce real contact/reference sheets and final provider
  prompts before attempting the movie.
- Recurring behavior should become skills/subagents, not bespoke scripts.

### YouTube Workflow Evidence

Transcript artifact:

```text
/tmp/youtube-7qBYe_VX_lE/transcript.json
```

Video metadata:

```text
Title: I gave Seedance 2.0 my entire storyboard. Here's what happened.
Channel: Edit Illusions
Upload date: 2026-06-09
Duration: 703 seconds
Extraction method: direct
```

Workflow evidence from transcript:

- Around 21-36 seconds: use an LLM to turn a story idea into a storyboard image
  prompt with a defined panel grid.
- Around 57-84 seconds: generate a 16:9 / 4K storyboard board image; GPT image
  output was preferred for realism in the example.
- Around 106-132 seconds: create a character sheet with multiple angles and
  expressions before placing the character into the storyboard/video workflow.
- Around 298-320 seconds: feed the storyboard image and character sheet to the
  video provider with a concise prompt that asks the provider to follow the
  storyboard panel by panel while maintaining character consistency.
- Around 635-685 seconds: this workflow is positioned as faster/cheaper for
  proofing and concepts; frame-by-frame or multi-image-per-shot workflows offer
  more control but cost more time and credits.

## Official Kling Source Assessment

Sources checked:

- `https://kling.ai/quickstart/klingai-video-3-omni-model-user-guide`
- `https://kling.ai/document-api/quickStart/productIntroduction/overview`

Findings for this pipeline:

- The creator-facing Omni guide supports a storyboard-first pattern where
  reference images/elements are paired with explicit prompt text describing
  shot duration, camera movement, subject action, dialogue, and sound.
- Emotional direction should be written into the shot text as visible physical
  behavior and pacing. For example: a character hesitates, inhales, tightens
  their jaw, drops their shoulders, or pauses before speaking.
- Character voice can be grounded with uploaded audio/video references in the
  creator workflow, but this dry-run has not selected voice reference files.
- The API overview is a separate automation contract. The current dry-run does
  not claim API-submit readiness; a future `$kling-video` stage must map the
  provider packet into the exact API request shape and preserve upload/task
  receipts.

Pipeline consequence:

- `$create-story` records emotional intent.
- `$create-storyboard` converts that intent into Kling-facing panel text:
  physical emotional behavior, camera, pause/timing, and dialogue delivery.
- `$provider-packet` must include both the storyboard image and the scene
  directions text before any live provider step can be considered.

## Implemented vs Intended vs Missing

1. Story seed and story contract
   - Status: `PARTIAL`
   - Current behavior: `persona-dream` can produce dream story artifacts, and
     `$create-story` exists for richer story development.
   - Intended behavior: the human seed becomes an accepted `story_contract.md`
     and `story_contract.json` before visual generation.
   - Gap: the Horus/Embry run advanced into assets before the story/visual
     contract was stable enough.

2. Visual entity extraction
   - Status: `PARTIAL`
   - Current behavior: entities were represented across ad hoc artifacts and a
     later `story_visual_package` shape.
   - Intended behavior: extract a keyed JSON object for characters, creatures,
     scenery, props, and effects.
   - Required shape:

```json
{
  "characters": {
    "horus": {
      "entity_id": "character_horus_lupercal_warmaster",
      "description": "Pre-Heresy Horus Lupercal, Warmaster of Warhammer 40,000, bald pale transhuman primarch, black-and-gold armor, warmer conversational state.",
      "image_file_paths": [],
      "source_urls": [],
      "visual_anchors": ["Horus Lupercal", "Warmaster", "Warhammer 40,000", "bald", "black armor", "gold trim"],
      "must_not_include": ["generic space marine", "dark-haired soldier", "corrupted monster"]
    }
  },
  "creatures": {
    "tyranids": {
      "entity_id": "creature_warhammer_40k_tyranids_background",
      "description": "Warhammer 40,000 Tyranids as background creatures, chitin carapace, scything talons, hive-organism silhouettes, playful motion but still canon-grounded.",
      "image_file_paths": [],
      "source_urls": [],
      "visual_anchors": ["Warhammer 40,000 Tyranids", "chitin", "scything talons", "hive swarm"],
      "must_not_include": ["generic cute aliens", "dinosaurs", "insects without 40k silhouette"]
    }
  },
  "scenery": {
    "void_world_patio": {
      "entity_id": "environment_void_world_patio_tea_terrace",
      "description": "Small patio table with umbrella on a surreal void world terrace, cinematic sci-fi atmosphere, SPARTA Explorer work context."
    }
  },
  "props": {
    "tea_table": {
      "entity_id": "prop_patio_table_umbrella_tea_sparta_laptop",
      "description": "Patio table, umbrella, tea service, laptop or tablet showing SPARTA Explorer interface."
    }
  }
}
```

3. Canon/reference research
   - Status: `PARTIAL`
   - Current behavior: Brave Search was added conceptually and used manually in
     the conversation, but it was not enforced as a pre-generation gate for all
     canon-sensitive prompts.
   - Intended behavior: `$casting-agent` runs memory/project reference lookup
     first, then Brave Search fallback for missing or insufficient references.
   - Gap: generated prompts were too ambiguous, which allowed Horus/Tyranids to
     genericize.

4. Casting and reference sheets
   - Status: `PARTIAL_FAILED_REVIEW`
   - Current behavior: a contact-sheet index and provider matrix exist, but
     screenshots show the human-facing artifact is not acceptable.
   - Intended behavior: `$casting-agent` produces a `casting_contract.json`,
     `chosen_reference_inputs.json`, and `contact_sheet_work_order.json`; then
     `$contact-sheet` produces real sheet-style references.
   - Gap: the review artifact should look like production reference sheets:
     2-4 provider images per Kling Element plus an optional human review grid,
     not stretched cards.

5. Storyboard board
   - Status: `MISSING`
   - Current behavior: `$create-storyboard` exists, but its generated panel
     fidelity is documented as not implemented.
   - Intended behavior: a storyboard-first mode creates a single 16:9 board
     image with 8-15 panels, timing, and concise panel descriptions.
   - Gap: this is the most important missing artifact from the YouTube-derived
     workflow.

6. Provider prompt packet
   - Status: `PARTIAL`
   - Current behavior: `provider_inputs.json` and dry-run receipts exist for
     some lanes.
   - Intended behavior: provider packet contains the storyboard board image,
     selected reference sheets/panels, final Kling prompt, timing, dialogue,
     negative constraints, and upload/submit readiness checks.
   - Gap: the packet is backend-heavy and not yet centered on the storyboard +
     reference-sheet model.

7. Kling video generation
   - Status: `MISSING`
   - Current behavior: no accepted Kling MP4 with upload, queue, response,
     download, ffprobe, frame sheet, and manual review receipt exists for this
     story.
   - Intended behavior: a narrow provider runner or `$create-movie` lane submits
     the provider packet and records all receipts.
   - Gap: dry-run provider receipts are not video-generation proof.

8. Review and learning
   - Status: `PARTIAL`
   - Current behavior: review pages exist but became a distraction from the core
     artifact failure.
   - Intended behavior: review page is a final inspection surface for actual
     storyboard/reference/video artifacts, not a substitute for them.
   - Gap: visual acceptance must inspect real screenshots/frame sheets.

## Proposed Skill And Subagent Ownership

### `$create-story`

Owns:

- Expand seed into accepted story.
- Produce short story contract, screenplay/timed beats, dialogue, and scene
  descriptions.
- Preserve narrative emotional intent and dialogue intent. For Persona-Dream
  story drafting, prefer `$scillm` one-shot `model: moonshot-text` (Moonshot
  Kimi K2.6) when available.

Does not own:

- Canon image research.
- Contact/reference sheet generation.
- Kling-specific camera movement, physical performance direction, provider shot
  text, or panel-level pause notation.
- Provider submission.

### `$casting-agent`

Owns:

- Intake `story_visual_package.json`.
- Validate required story/context/entity fields.
- Recall provided or prior accepted references.
- Run Brave Search fallback for missing canon-sensitive references.
- Write `casting_contract.json`, `chosen_reference_inputs.json`, and
  `contact_sheet_work_order.json`.
- Review generated sheets against the contract and retry within budget.

This should be the modular debugging boundary for visual identity failures.

### `$contact-sheet`

Owns:

- Convert `contact_sheet_work_order.json` into image prompts, generated panels,
  sheet grids, provider-ready element packs, and manifests.
- Preserve raw prompts, image receipts, image paths, sizes, and review notes.
- Build human-readable sheets without stretching or aspect distortion.

Required amendment:

- Add explicit modes for `reference-sheet-grid` and `storyboard-board` or split
  storyboard board into `$create-storyboard`.
- Treat the current card gallery as secondary debug output, not the main
  acceptance artifact.

### `$create-storyboard`

Owns:

- Convert accepted story/timed beats into a storyboard prompt and storyboard
  image board.
- Convert narrative emotional intent into provider-facing panel text that
  describes visible physical emotion, camera movement, and pause/timing in
  plain language.

Required amendment:

- Add a deterministic storyboard-board mode:

```text
story_contract + timed beats + selected references
-> storyboard_prompt.md
-> storyboard_board.png
-> storyboard_board_receipt.json
-> kling_scene_directions.md
-> kling_scene_payloads.json
```

`kling_scene_directions.md` is the provider-facing text to pair with the board.
`kling_scene_payloads.json` is an internal validation artifact; it fails closed
when any panel lacks physical emotional behavior, camera movement, pause/timing
text, or provider-facing panel text.

The current generated-fidelity and shot-direction gaps must be closed before
this skill can support the YouTube-derived workflow.

### `$create-image` and `$scillm`

Own:

- Headless image generation for reference sheets and storyboard boards.
- Preserve prompt-file, backend, response, output image, and normalization
  receipt.

Rules:

- Default must preserve aspect ratio.
- Never silently stretch.
- Generated images must be inspected or measured before acceptance.

### `$create-movie` or new `$kling-video`

Owns:

- Provider-specific video generation after story, storyboard, references, and
  prompt packet exist.

Assessment:

- `$create-movie` is broad and local-model oriented.
- A narrower `$kling-video` or `$provider-prompt` skill may be cleaner for:
  upload receipts, provider request JSON, queue events, response JSON,
  download receipt, `output.mp4`, `ffprobe.json`, and `frame_sheet.jpg`.

### `$review-page`

Owns:

- Review surface after artifacts exist.

Does not own:

- Replacing missing storyboards, reference sheets, or video receipts with a
  dashboard.

## Recommended Pipeline

```text
0. $persona-dream idea synthesis -> idea_contract.json
1. $create-story -> story_contract.md + story_contract.json + timed beats
2. Entity extractor -> story_visual_package.json
3. $casting-agent -> casting_contract.json + chosen_reference_inputs.json
4. $contact-sheet / $create-image / $scillm -> reference sheets and provider element images
5. $create-storyboard / $create-image / $scillm -> storyboard_board.png
6. Provider packet builder -> final_kling_prompt.md + provider_request_dry_run.json
7. Kling live submit only after dry-run readiness -> output.mp4 + receipts
8. Review page -> storyboard, reference sheets, frame sheet, video, receipts
9. Memory/Qdrant pointers only after accepted visual review
```

Stage 0 is autonomous by default. `persona-dream` should synthesize the initial
idea from persona memories, project knowledge in `$memory`, recent project
activity, and optional `$brave-search` context for relevant events or
canon-sensitive grounding. A human or project agent may pass a specific idea,
but that is an override path and must be recorded in `idea_contract.json` as
`source_mode: human_supplied_seed` or `project_agent_supplied_seed`.

For codebase-grounded dreams, Stage 0 asks project questions through `$memory`
using `/recall`; it does not inspect live git or the filesystem itself. The
idea contract must record the question pattern, `scope`, optional collections,
and observed recall metadata. Required patterns:

```text
general project state: /recall q="what did we work on recently..." scope=<project>
project activity: /recall collections=["project_activity"]
code structure/symbols: /recall collections=["code_symbols"]
```

If the needed commits or symbols are not already in memory, Stage 0 blocks or
requests ingestion, for example `memory-agent activity ingest-git ...`, before
using code activity as dream source material.

## Worked Example: Horus/Embry Storyboard-First Dry-Run Fixture

This is a target fixture and reference implementation trace. It is not evidence
that the artifacts already exist.

Seed:

```text
Horus and Embry have tea under a patio umbrella on a Warhammer 40k void world
while Tyranids run/play in the background and they discuss SPARTA Explorer.
```

| Stage | Owning subagent / skill | Example input | Example output | Acceptance gate | Rollback target |
| --- | --- | --- | --- | --- | --- |
| 0. Idea synthesis | `$persona-dream` | Persona memories, project memory, recent project activity, optional Brave context, or explicit supplied seed | `idea_contract.json` | Source mode declared; memory/project inputs or supplied seed recorded; chosen idea preserved | Memory/project recall set or supplied seed |
| 1. Story contract | `$create-story` | `idea_contract.json` | `story_contract.json`, `timed_beats.json` | Story schema passes; seed preserved; speakers identified | Idea contract |
| 2. Entity extraction | `$casting-agent extract` | `story_contract.json`, `timed_beats.json` | `story_visual_package.json` | Horus, Embry, Tyranids, void world patio, tea table, SPARTA laptop keyed | Accepted story contract |
| 3. Casting/reference research | `$casting-agent` | `story_visual_package.json` | `casting_contract.json`, `chosen_reference_inputs.json`, `contact_sheet_work_order.json` | Horus/Tyranids have human, memory, local, or Brave-backed references | Entity package |
| 4. Reference sheets | `$contact-sheet` + `$create-image` / `$scillm` | `contact_sheet_work_order.json` | `horus_reference_sheet.png`, `embry_reference_sheet.png`, `tyranid_environment_reference_sheet.png`, `layout_validation.json` | No stretching; dimensions recorded; visual identity manually accepted | Casting contract |
| 5. Storyboard board + scene directions | `$create-storyboard` + `$create-image` / `$scillm` | Accepted story, timed beats, accepted references | `storyboard_prompt.md`, `storyboard_board.png`, `storyboard_board_receipt.json`, `kling_scene_directions.md`, `kling_scene_payloads.json` | 16:9 board; 10-12 panels; beat-to-panel map; every panel has physical emotion, camera, pause/timing, provider text; manual storyboard acceptance | Accepted references or story contract |
| 6. Provider packet | `$provider-packet` | Accepted story, references, storyboard, scene directions | `final_kling_prompt.md`, `provider_request_dry_run.json`, `referenced_artifacts.lock.json`, `readiness_receipt.json` | All paths exist; hashes locked; scene directions/payloads present; upstream accepted; `paid_call_performed: false` | Accepted storyboard/reference checkpoint |
| 7. Live provider execution | `$kling-video` | Accepted provider packet + human approval | `upload_receipts.json`, `provider_queue_events.jsonl`, `provider_response.json`, `output.mp4`, `ffprobe.json`, `frame_sheet.jpg` | Approval exists; MP4 downloaded; frame sheet reviewed | Provider packet; no paid retry without approval |
| 8. Review display | `$review-page` | Existing accepted artifacts | Review page / inspection surface | Shows real artifacts and receipts only | Does not create or repair artifacts |

### Example Orchestration Trace

0. `persona-dream` synthesizes or accepts the idea.
   - Default input: persona memory, project knowledge in memory, recent project
     activity, and optional Brave Search context.
   - Override input: raw human/project-agent seed.
   - Output: `idea_contract.json`.
   - Deterministic checks: source mode is declared, input sources are recorded,
     chosen idea text exists, and autonomous runs have memory/project source
     links before story generation.
   - Codebase questions: ask `/recall` with natural-language project questions,
     `scope`, and optional `project_activity` / `code_symbols` collections; do
     not treat memory as live filesystem or git inspection.
   - Manual review: optional human override of the selected idea.
   - Allowed status after automated validation: `ACCEPTED_AUTOMATED` or
     `BLOCKED`.
   - Rollback: memory/project recall set or supplied seed.

1. `persona-dream` invokes `$create-story`.
   - Input: `idea_contract.json`.
   - Output: `story_contract.json`, `timed_beats.json`.
   - Deterministic checks: JSON schema passes, seed is preserved, target
     duration is declared, speakers are identified.
   - Manual review: story is accepted as the Horus/Embry patio premise.
   - Allowed status after automated validation: `ACCEPTED_AUTOMATED`.
   - Rollback: return to the human seed.

2. `persona-dream` invokes `$casting-agent extract`.
   - Input: accepted story artifacts.
   - Output: `story_visual_package.json`.
   - Required entities:
     - `character_horus_lupercal_warmaster`
     - `character_embry`
     - `creature_warhammer_40k_tyranids_background`
     - `environment_void_world_patio_tea_terrace`
     - `prop_patio_table_umbrella_tea_sparta_laptop`
   - Deterministic checks: required entities are keyed, descriptions exist,
     optional image paths exist when supplied.
   - Manual review: entity list matches the accepted story scope.
   - Allowed status: `ACCEPTED_AUTOMATED` or `FAILED_AUTOMATED_CHECK`.
   - Rollback: accepted story contract.

3. `$casting-agent` performs reference sufficiency checks.
   - Input: `story_visual_package.json`.
   - Reference priority:
     - Human/project references first.
     - Memory/Qdrant accepted references second.
     - Project-local artifacts third.
     - Brave Search only for missing canon-sensitive references.
     - Provisional generated placeholders only when explicitly marked.
   - Output: `casting_contract.json`, `chosen_reference_inputs.json`,
     `contact_sheet_work_order.json`.
   - Deterministic checks: Horus and Tyranids have sufficient reference
     provenance or a blocked receipt; visual anchors and `must_not_include`
     constraints are propagated into downstream prompt requirements.
   - Manual review: reference strategy matches the story state, such as
     pre-Heresy warmer Horus rather than corrupted Horus.
   - Allowed status: `ACCEPTED_MANUAL`, `BLOCKED`, or
     `FAILED_MANUAL_REVIEW`.
   - Rollback: entity package.

4. `$contact-sheet` generates accepted reference sheets.
   - Input: `contact_sheet_work_order.json`.
   - Output:
     - `horus_reference_sheet.png`
     - `embry_reference_sheet.png`
     - `tyranid_environment_reference_sheet.png`
     - `layout_validation.json`
     - prompt and image-generation receipts
   - Deterministic checks: raw dimensions recorded, placed-cell dimensions
     recorded, nonuniform scaling rejected, minimum side >= 300 px, provider
     image counts match the Kling Element rules.
   - Manual review: Horus is not stretched or genericized, Tyranids remain
     Warhammer 40k-grounded, and Embry matches the persona visual contract.
   - Failure example: if Horus is stretched, genericized, or missing
     black-and-gold Warmaster anchors, the sheet status becomes
     `FAILED_MANUAL_REVIEW`; downstream storyboard/provider artifacts cannot
     consume it.
   - Allowed status: `GENERATED_UNREVIEWED`, `ACCEPTED_MANUAL`, or
     `FAILED_MANUAL_REVIEW`.
   - Rollback: casting contract.

5. `$create-storyboard board` generates the storyboard board and Kling scene
   directions.
   - Input: accepted story, timed beats, accepted reference manifest.
   - Output:
     - `storyboard_prompt.md`
     - `storyboard_board.png`
     - `storyboard_board_receipt.json`
     - `kling_scene_directions.md`
     - `kling_scene_payloads.json`
   - Deterministic checks: 16:9 image ratio, declared 10-12 panel count,
     beat-to-panel mapping, panel labels/timing/captions present or explicitly
     failed, and every panel has physical emotional behavior, camera movement,
     pause/timing text, and provider-facing shot text.
   - Manual review: board depicts the patio tea scene, Tyranids in the
     background, and SPARTA Explorer discussion.
   - Allowed status: `GENERATED_UNREVIEWED`, `ACCEPTED_MANUAL`, or
     `FAILED_MANUAL_REVIEW`.
   - Rollback: accepted references or story contract depending on failure
     source.

6. `$provider-packet` builds the dry-run Kling packet.
   - Input: accepted story, accepted references, accepted storyboard board, and
     accepted scene directions.
   - Output:
     - `final_kling_prompt.md`
     - `provider_request_dry_run.json`
     - `referenced_artifacts.lock.json`
     - `readiness_receipt.json`
   - Deterministic checks: all paths exist, artifact hashes are locked,
     storyboard image plus scene directions/payloads are present, upstream
     receipts are accepted, dialogue/duration exist for speaking shots,
     provider/model/version are declared, and
     `paid_call_performed: false`.
   - Manual review: packet accurately describes the accepted storyboard and
     does not smuggle in unreviewed references.
   - Allowed status on pass: `PROVIDER_PACKET_ACCEPTED`.
   - Rollback: accepted storyboard/reference checkpoint.
   - Paid provider calls are not allowed in this stage.

7. `$kling-video` remains blocked until explicit approval.
   - Required input:
     - `paid_call_approval_receipt.json`
     - accepted provider packet
   - Output after approved live run:
     - `upload_receipts.json`
     - `provider_queue_events.jsonl`
     - `provider_response.json`
     - `download_receipt.json`
     - `output.mp4`
     - `ffprobe.json`
     - `frame_sheet.jpg`
     - `manual_video_review_receipt.json`
   - Deterministic checks: approval exists, input hashes match the accepted
     provider packet, MP4 exists, duration is checked, frame sheet is generated.
   - Manual review: Horus/Embry identity, Tyranids, lip sync, and visual quality
     are accepted.
   - Allowed status without approval: `BLOCKED`.
   - Allowed status after accepted render: `LIVE_RENDER_ACCEPTED`.
   - Rollback: provider packet; no paid retry without approval.

8. `$review-page` displays the artifacts.
   - Input: existing accepted artifacts and receipts.
   - Output: review page or inspection surface.
   - Deterministic checks: visible page references real files; missing artifacts
     are shown as missing; no fake status values are introduced.
   - Manual review: page shows the story, reference sheets, storyboard, provider
     packet, frame sheet, video, and receipts when those artifacts exist.
   - Allowed status: `ACCEPTED_MANUAL` only for the display surface, not for the
     underlying video pipeline.
   - Rollback: none; `$review-page` does not create or repair artifacts.

## Acceptance Gates

Gate 1: Story acceptance

- `story_contract.md`
- `story_contract.json`
- `timed_beats.json` or equivalent
- Human or reviewer acceptance note

Gate 2: Entity extraction acceptance

- `story_visual_package.json`
- All required entities keyed with descriptions
- Provided image paths or source URLs recorded

Gate 3: Casting acceptance

- `casting_contract.json`
- `chosen_reference_inputs.json`
- `contact_sheet_work_order.json`
- Brave Search receipts for Horus and Tyranids unless provided references are
  sufficient and recorded

Gate 4: Reference sheet acceptance

- Real PNG sheets or separate provider images
- No stretched images
- Minimum image-size checks
- Human-facing sheet screenshot or image inspection note
- Failed sheets generate bounded retry receipts, not acceptance

Gate 5: Storyboard board acceptance

- `storyboard_prompt.md`
- `storyboard_board.png`
- Board is 16:9, contains panel numbers/timing/captions, and reflects accepted
  story beats

Gate 6: Provider dry-run readiness

- `final_kling_prompt.md`
- `provider_request_dry_run.json`
- All referenced image paths exist
- Dialogue/duration present for speaking shots
- `paid_call_performed: false`

Gate 7: Kling render evidence

- Upload receipts
- Queue events
- Provider response
- Download receipt
- `output.mp4`
- `ffprobe.json`
- `frame_sheet.jpg`
- Manual visual review receipt

## Questions For WebGPT Review

1. Is this decomposition the right modular boundary between `$create-story`,
   `$casting-agent`, `$contact-sheet`, `$create-storyboard`, and a Kling runner?
2. Should storyboard board generation live in `$create-storyboard`, or should
   `$contact-sheet` own both reference sheets and storyboard board grids?
3. Is a new `$kling-video` / `$provider-prompt` skill justified, or should this
   remain inside `$create-movie`?
4. What deterministic tests or fixtures should be added first so a project
   agent cannot regress into stretched images, missing storyboard board, or
   ambiguous Horus/Tyranid prompts?
5. What is the smallest next implementation slice that produces useful proof:
   a corrected Horus reference sheet, a storyboard board, or a full dry-run
   provider packet?

## Proposed Next Slice

Recommended next slice before any live Kling call:

```text
Create a deterministic storyboard-first fixture for the Horus/Embry seed:
story_visual_package.json
-> casting_contract.json
-> one Horus reference sheet
-> one Embry reference sheet
-> one Tyranid/environment/prop sheet
-> one 10-12 panel storyboard_board.png
-> final_kling_prompt.md
-> provider_request_dry_run.json
```

This slice should be considered ready for live provider execution only after
the storyboard board and reference sheets pass visual inspection.
