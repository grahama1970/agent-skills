---
name: create-kling-scene
description: >
  Compose a Kling video request from a pydantic-validated scene table and
  per-character reference images, with no bespoking. Use when a user says
  create a kling scene, make a kling video from a scene table, compile a
  scene script to kling, or wants the scene-writing -> kling pipeline run
  as one gated command instead of hand-built requests.
triggers:
  - create a kling scene
  - make a kling video from this scene
  - compile scene table to kling
  - kling scene pipeline
provides:
  - kling-scene-composition
composes:
  - interview
  - best-practices-scene-script-writing
  - best-practices-kling-video
  - triage-error
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-kling-video
  - best-practices-scene-script-writing
runtime_self_improvement: basic
---

# create-kling-scene

One gated command from scene script to submittable Kling packet. Creating a
Kling video no longer requires bespoke request assembly — it requires two
specific inputs and everything else is deterministic:

```text
INPUT 1: scene table   (scene_script.scene_table.v1 — must pass the
                        scene-script-writing pydantic gate)
INPUT 2: references    (one single-subject crop per character row —
                        validated as real decodable PNG/JPEG, magic bytes,
                        >=1KB, not just an existing path)
INPUT 3: voice wavs    (optional --voice name:purpose=/path.wav — validated as real
                        RIFF/WAVE within Kling bounds: 2-60s lipsync,
                        5-30s voice_clone)
   |
   v
./run.sh build --scene scene.json --refs embry=/path/embry.png --out-dir /path/run
   |
   1. scene_table_gate    scene-script-writing pydantic validate (fail-closed)
   2. reference_check     every character row has exactly one existing ref
   3. instructions_gate   create_kling_scene.instructions.v1 — typed FINAL
                          instructions (per-slot char budgets, @ElementN
                          binding coverage, character<->ref<->voice cross-
                          checks, required_fact_ids coverage) validated BEFORE any Kling-format
                          conversion; emitted as kling_instructions.json
   4. compile             MECHANICAL instructions -> kling_video.request.v1
                          (no decisions below the validated layer)
   5. kling_packet_gate   kling-video pydantic validate (endpoint/element/
                          budget/URL rules)
   |
   v
receipt.json (create_kling_scene.receipt.v1) + kling_request.json
+ next_command for the PAID submit (never auto-submitted)
```

Every stage failure carries pydantic `errors[]` AND a triage-error
classification (`{code, cause, next_command}`); ambiguous signals self-heal by
minting a provisional catalog code. When triage cannot fix it (unrecoverable,
freshly minted unclassified code, or classifier unavailable), the receipt gains
`needs_attention` with an $interview handoff: `interview_questions.json` is
written beside the receipt and `resume_hint` runs the interview. The receipt is
typed (`create_kling_scene.receipt.v1`, pydantic extra=forbid, producer-side
seam_validation stamp), never prose.

## Fact coverage contract

All environment header fields and every element row in the scene table become `required_fact_ids` by default.
`kling_instructions.json` must list the same IDs in `covered_fact_ids`; otherwise `instructions_gate` BLOCKS before any provider packet is written. Lower-priority mood/style cuts belong in `dropped_desired_fact_ids`, never by silently losing required rows during prompt condensation.

## What this skill refuses to do

- Accept prose instead of a scene table (no table -> `scene_table_gate` BLOCKED).
- Accept a character without a reference image (`reference_check` BLOCKED).
- Describe character identity in prompt prose (identity travels in `elements[]`).
- Submit. `build` stops at a validated packet; the paid call is the human/agent
  running the emitted `next_command` (kling-video `submit`), per Rule 9
  no-silent-retry.

## Commands

```bash
./run.sh build --scene scene.json --refs embry=/abs/embry.png horus=/abs/horus.png --voice embry:lipsync=/abs/embry.wav --out-dir /mnt/storage12tb/skills/create-kling-scene/outputs/<run>
./sanity.sh   # offline positive + negative fixtures
```

## Ownership

Scene writing rules: best-practices-scene-script-writing. Kling mechanics,
budgets, and the paid submit: best-practices-kling-video. Failure taxonomy:
triage-error. This skill owns only the composition order and the receipt.
