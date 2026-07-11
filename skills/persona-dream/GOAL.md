# Persona Dream Goal

## Objective

Make `persona-dream` a reliable, receipt-backed short dream/video pipeline that
a project agent can run without hand-building one-off JSON files, prompts,
contact sheets, provider packets, or review pages.

The skill should turn persona memory and project context into reusable
artifacts:

```text
persona/context seed
-> story contract
-> visual/audio entity contracts
-> reference images and contact sheets
-> cinematic technique selection / Script DNA / Look Lock
-> storyboard and timed dialogue
-> provider-ready prompt packets
-> provider receipts / clip artifacts
-> review artifacts
-> memory and Qdrant pointers
```

`persona-dream` owns the dream-specific planning contract. It does not become a
general movie studio, voice trainer, or provider wrapper. It composes those
skills and records their receipts.

## Primary User Job

Given a seed such as:

```text
Horus and Embry have tea under a patio umbrella on a 40K void world while
Tyranids play in the background and they discuss SPARTA Explorer.
```

the project agent should be able to produce the next valid pipeline artifact by
calling documented skill commands, not by inventing bespoke scripts.

## Non-Negotiable Rule

Do not leave recurring pipeline behavior as one-off run artifacts.

If a step is needed twice, promote it into a skill command, script, schema, or
template. Bespoke JSON construction is allowed only as a prototype for the next
reusable command.

## Skill Map

### Existing Skills To Use

`$persona-dream`
: Orchestrates the dream/video packet. Owns memory residue recall, story
contract, dream-specific continuity, timed transcript, multimodal prompt packet,
voice handoff plan, stage reports, and final receipt discipline.

`$memory`
: Recalls persona residue, prior project context, accepted visual assets, voice
state, and durable pointers. Memory stores metadata and paths, not image/vector
payloads.

`$contact-sheet`
: Owns visual reference generation and retrieval for persona-dream. It should
accept chosen references, fall back to Brave search when needed, plan GPT image
generation, build contact sheets with Pillow, write provider image manifests,
and index accepted image paths in memory/Qdrant.

`$best-practices-kling-contact-sheet`
: Governs Kling Element constraints: 2-4 separate images per Element, main
front/hero image first, supplementary angles/details, explicit Element
description, do-not-change list, ignore list, image size/file constraints, and
Kling prompt shape.

`$create-story`
: Creates or expands screenplay/story material when the human seed is not
already an accepted story contract.

`$create-storyboard`
: Converts an accepted story or screenplay into shot plans, camera framing,
timing, panels/animatics, and reviewable storyboard artifacts.

`$cinematic-technique-selector`
: Selects the Kling-friendly Director of Photography and Script DNA vocabulary
before storyboard/provider prompt text is written. It owns the Look Lock, camera
format, lens family, camera movement vocabulary, lighting, color grade,
composition, atmosphere, continuity locks, negative constraints, script rhythm,
dialogue pressure, conflict pattern, reveal logic, theme, and a shot bible.
`$memory` may recall prior accepted Look Locks and Script DNA selections and
store reviewed selections, but the selector skill's structured `data/` files
remain the source of truth for the technique catalogs.

`$create-image`
: Generates quality-sensitive still images when the local project-agent image
path is preferred.

`$scillm`
: Provides headless image/LLM calls with caller attribution, logging, receipts,
and backend routing. Use for GPT image or fast draft image backends when the
flow must be service-callable.

`$create-movie`
: Owns full movie assembly, audio/muxing, long-form review, and polished final
MP4 workflows when a dream sequence graduates beyond the bounded persona-dream
pipeline.

`$tts-horus`, `$train-voice`, `$voice-lab`, `$learn-voice`
: Own voice existence checks, voice training/conversion, voice evaluation, and
speaker-specific audio artifacts when a dream has spoken characters.

`$brave-search`
: Provides raw web/image search receipts for canon-sensitive entities when no
accepted reference image is supplied.

`$dogpile`
: Optional escalation only. Use it when the dream needs broader multi-source
research across web, papers, videos, GitHub, or historical sources. Do not use
it as the default reference/canon lookup path for persona-dream because
`$brave-search` gives simpler raw receipts that are easier to attach to
casting/contact-sheet gates.

### Existing Skills To Amend

`$contact-sheet` should gain reusable commands for the reference workflow:

```bash
./run.sh contact-sheet add-reference --asset-root <root> --entity-id <id> --image <path-or-url>
./run.sh contact-sheet select-references --asset-root <root>
./run.sh contact-sheet plan-generation --asset-root <root>
./run.sh contact-sheet generate --asset-root <root> --backend gpt-image
./run.sh contact-sheet build --asset-root <root>
./run.sh contact-sheet provider-dry-run --provider-inputs <provider_inputs.json>
```

`$persona-dream` should call these commands instead of hand-writing
`brave_image_candidate_selection.json`,
`gpt_contact_sheet_generation_plan.json`, or provider packets.

`$create-storyboard` may need a deterministic/non-collaborative mode for
persona-dream when the story contract is already accepted and the next artifact
must be a machine-readable shot plan rather than an open creative dialogue.

### Likely New Skills

`$provider-prompt`
: Converts storyboard + timed transcript + accepted reference assets into
provider-specific request packets for Kling, Seedance, lip-sync lanes, and
future hosted video providers. It should produce dry-run receipts before any
paid call.

`$dream-voice-cast`
: Determines speaking characters, checks for existing accepted voice assets,
routes missing voices to the correct voice workflow, and emits a
`voice_handoff_plan.json`.

These should be created only if the behavior becomes broad enough that
`$persona-dream` or `$create-movie` would otherwise keep growing provider- or
voice-specific code.

## Target Pipeline

### 1. Seed Dream

Inputs:

```text
persona id
optional secondary persona id
human seed idea
optional recent commits scope
optional memory topic
```

Outputs:

```text
dream_request.json
residue_links.json
contradiction_report.json
seed_receipt.json
```

Rules:

- Use `$memory` first for persona facts and prior lessons.
- Use recent GitHub commits only when requested or when the run mode says to.
- Do not fabricate residue.

### 2. Write Story Contract

Outputs:

```text
story_contract.md
story_contract.json
```

Rules:

- Preserve the human seed.
- Label agent-authored story material.
- Keep source/persona facts separate from synthetic dream content.
- If the story is not accepted, do not advance to contact sheets.

### 3. Extract Entities

Outputs:

```text
visual_entities.json
audio_entities.json
scene_bindings.json
```

Entity groups:

```text
characters
creatures
environments
objects/props
effects
speaking roles
```

Rules:

- Canon-sensitive entities require identity contracts.
- Speaking characters require voice-state checks.

### 4. Build Visual References With `$contact-sheet`

Preferred flow:

```text
entity contract
-> chosen reference image if supplied or recalled
-> Brave search fallback only when needed
-> image candidate selection / quality gate
-> GPT generation plan
-> GPT-generated 2-4 clean panels per Kling Element
-> Pillow contact_sheet_index.png for human review
-> separate provider image paths for Kling/Seedance
```

Required artifacts:

```text
reference_inputs.json
brave_search_receipts/*.json
brave_image_receipts/*.json
identity_contracts/*.json
brave_image_candidate_selection.json
gpt_contact_sheet_generation_plan.json
prompts/*.prompt.md
images/<element_id>/*.png
receipts/*.json
reference_asset_manifest.json
contact_sheet_index.png
provider_matrix.png
visual_entity_context.json
provider_inputs.json
```

Rules:

- If a project agent or human supplies an accepted reference image, use it after
quality and rights/identity checks. Do not force Brave search.
- If no accepted reference exists for a canon-sensitive entity, use
`$brave-search` and store raw receipts.
- Use `$best-practices-kling-contact-sheet` for every Kling-ready pack.
- For Kling, provider inputs are separate panel images, not a dense grid.
- Contact sheets are human review artifacts.

### 5. Cast Voices

Outputs:

```text
voice_handoff_plan.json
voice_state_receipt.json
```

Rules:

- Determine which characters speak before provider prompting.
- Use existing accepted voices when available.
- Route missing voices to the correct voice skill.
- Keep consent, reference provenance, and voice identity boundaries explicit.

### 6. Select Cinematic Technique And Script DNA

Use `$cinematic-technique-selector` after story/entity extraction and before
storyboard prompt text.

Outputs:

```text
technique_selection.json
script_dna_selection.json
look_lock.json
shot_bible.json
```

Rules:

- The DoP layer selects camera format, lens, lighting, color grade, atmosphere,
  movement grammar, composition, and continuity locks.
- The Script DNA layer selects story rhythm, dialogue pressure, scene engine,
  conflict pattern, reveal logic, irony, and theme.
- Writer/director names are allowed only as internal craft shorthand and must
  be translated into prompt-ready technique language.
- Do not imitate a living writer's exact voice.
- Do not advance to storyboard if speaking scenes lack Script DNA.

### 7. Storyboard And Timing

Use `$create-storyboard` when an accepted screenplay/story must become a shot
plan or animatic.

Outputs:

```text
storyboard.json
timed_transcript.json
camera_plan.json
script_dna_bindings.json
shot_reference_bindings.json
animatic or review panels when requested
```

Rules:

- Storyboard timing must bind to exact dialogue and Script DNA beat rules.
- Each shot must state required visual Elements.
- Do not generate provider prompts from an unaccepted storyboard.

### 8. Provider Prompt Packet

Outputs:

```text
provider_inputs.json
provider_dry_run/<scene_id>/<lane_id>/provider_request_dry_run.json
provider_dry_run/provider_dry_run_manifest.json
```

Rules:

- Dry-run receipts must set `paid_call_performed: false`.
- Provider packets must point to actual accepted image paths.
- Kling packets must preserve Element descriptions, do-not-change lists, ignore
lists, timing, and exact dialogue.
- Seedance/Kling/lip-sync lanes must remain comparable when used in a bakeoff.

### 9. Render Provider

Outputs for live calls:

```text
upload_receipts.json
provider_queue_events.jsonl
provider_response.json
download_receipt.json
output.mp4
ffprobe.json
frame_sheet.jpg
frame_sheet_receipt.json
provider_submit_receipt.json
```

Rules:

- A paid call requires explicit live mode.
- Do not bypass `provider_request_dry_run.json`.
- Do not claim success until the downloaded clip, duration proof, frame sheet,
and review receipt exist.

### 10. Assemble And Review

Outputs:

```text
assembled_output.mp4
ffprobe.json
frame_sheet.jpg
review_page/
manual_review_receipt.json
```

Rules:

- Use FFmpeg for clip stitching/muxing when needed.
- Stitch clips/video, not still images, unless producing a storyboard preview.
- Final video remains pending until manually or visually reviewed.

### 11. Persist Accepted Assets

Outputs:

```text
memory_upsert_receipt.json
qdrant_upsert_receipt.json
reference_asset_manifest.json
```

Rules:

- Store generated images on `/mnt/storage12tb`.
- Memory stores canonical metadata and pointers only.
- Qdrant stores vectors for image/text recall.
- Do not store vector arrays in memory/ArangoDB.

## Artifact Gates

Do not advance unless the prior gate has deterministic evidence:

```text
story accepted
visual/audio entities extracted
identity/reference contracts complete
Script DNA and Look Lock selected
contact sheets generated and visually reviewed
storyboard/timing accepted
provider dry-run ready
live provider receipts saved
clip frame sheet reviewed
memory/Qdrant writes receipted when requested
```

## Success Criteria

The goal is not merely to produce a clip. The goal is a repeatable project-agent
pipeline where each step has:

```text
documented command
input schema
output schema
receipt
failure mode
next-step contract
```

The skill is successful when the project agent can run a new persona-dream
video without bespoke artifact construction.

## Current Gap List

Known gaps to close:

```text
1. Promote Brave image candidate selection into $contact-sheet.
2. Add chosen-reference override support to $contact-sheet.
3. Add GPT contact-sheet generation planning to $contact-sheet.
4. Add GPT panel generation receipts to $contact-sheet.
5. Add Pillow review-sheet assembly and validation gates to $contact-sheet.
6. Add provider packet generation from accepted image paths.
7. Decide whether provider packet generation belongs in $contact-sheet,
   $persona-dream, or a new $provider-prompt skill.
8. Add deterministic storyboard/timing handoff between $persona-dream and
   $create-storyboard.
9. Add Script DNA handoff between story contract and storyboard.
10. Add voice existence/casting handoff before provider prompt creation.
11. Add sanity fixtures for the full no-paid-call pipeline.
```

## Immediate Next Implementation Target

Amend `$contact-sheet` first.

Reason:

```text
The repeated bespoke work is currently in reference selection, chosen-reference
handling, GPT contact-sheet planning, image generation receipts, and provider
image manifest construction.
```

First useful command target:

```bash
./run.sh contact-sheet plan-generation --asset-root <root>
```

It should consume:

```text
visual_entities.json
identity_contracts/*.json
reference_inputs.json or brave_image_candidate_selection.json
story_contract.md
```

and write:

```text
gpt_contact_sheet_generation_plan.json
prompts/<element_id>.prompt.md
```

No paid provider call should be part of this target.
