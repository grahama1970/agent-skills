# Persona Dream Identity Continuity Gate Repair

## Controlling objective

Produce a working accepted Kling video from Persona Dream with every pipeline step persisted in Memory. The current live return must not be accepted because Embry visibly changes identity between approximately 0 and 3 seconds.

## Current failures

1. `EMBRY_IDENTITY_DRIFT_00_03`: the first three sampled frames and the following close shot visibly depict materially different versions of Embry.
2. `DIALOGUE_STORYBOARD_SYNC_FAILED`: Kai dialogue was mixed at 0 seconds although his cue belongs to SB_003 at 5.0-7.5 seconds.
3. `KAI_DELIVERY_FLAT`: the live Chatterbox receipt has no paralinguistic tag and resolved to neutral delivery.
4. The prior post-Kling continuity receipt incorrectly passed and final acceptance reached 42/42.

## Existing implementation to reuse

- `skills/persona-dream/scripts/phase07_storyboard_tau_node.py` has `_run_identity_continuity_review`, `_attach_identity_continuity_review`, and fail-closed accepted-frame validation.
- Locked references:
  - `phase_07_storyboard_live_tau/references/01-embry_character_sheet.jpg`
  - `phase_07_storyboard_live_tau/references/02-kai_character_sheet.png`
- Active provider frames and contact sheet:
  - `phase_11_submit_return/provider_return/ca90...c840f/watch-codex-vision/frames/`
  - `phase_11_submit_return/provider_return/ca90...c840f/frame_contact_sheet.png`
- Current finalizer: `skills/persona-dream/scripts/finalize_provider_return.py`
- Current Memory final acceptance producer: `skills/persona-dream/scripts/persist_immutable_goal_steps.py`
- Current persistence acceptance: `skills/persona-dream/scripts/persist_voice_handoff_memory.py`

## Required invariants

1. Reference qualification fails if one named character's contact sheet contains mutually inconsistent identities.
2. No storyboard or provider request may consume an unqualified identity reference set.
3. Post-provider qualification compares every identity-readable sampled appearance against the qualified reference and against adjacent appearances.
4. Missing face/identity evidence is failure or explicit non-readable coverage, never PASS by omission.
5. Any required character mismatch invalidates provider-return acceptance, final report, Memory final step, and Return UI accepted state.
6. Advisory model prose cannot alone upgrade the gate to PASS; exact inputs, outputs, hashes, per-character findings, and policy must be persisted.
7. No new paid provider call is permitted by this repair.

## Exact question

Design the smallest implementation that reuses the existing identity-review machinery and enforces both reference-set qualification and post-Kling temporal continuity. Specify:

1. exact insertion points and functions/files to change;
2. receipt schemas and required fields;
3. how to classify readable, non-readable, match, mismatch, and inconsistent-reference cases;
4. whether to use the existing VLM review, deterministic face embeddings, or a hybrid, with fail-closed thresholds and limitations;
5. how final acceptance and Memory must be invalidated for the current live return;
6. focused positive and negative tests;
7. a minimal repair order that does not make another provider call.

Do not propose dashboards, broad refactors, or a new orchestration system. Return an implementation plan and pseudocode precise enough for mechanical application.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260717T162613Z:affa6203>>>

Do not print anything after that marker.
