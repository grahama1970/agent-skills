# Review Context: Persona-Dream Panel Repair Gate

## Objective

Review the new `persona-dream-panel-repair-gate` subagent contract and the
related `persona-dream` provider/panel gate rules before the project agent
moves into actual panel regeneration and Kling provider-packet repair.

The human explicitly requires WebGPT review to pass before the next phase. The
review should be strict: if the subagent contract cannot prevent the repeated
failure mode, return `needs_changes` or `blocked`.

## Current Failure Mode

The current Horus/Embry Kling dry-run report is blocked. Prior WebGPT preflight
returned:

```json
{
  "verdict": "BLOCKED",
  "can_move_to_next_phase": false,
  "blocking_count": 10,
  "blockers": [
    "panel_1_embry_missing",
    "unreviewed_panels_blocking",
    "panel_9_failed_state",
    "pasted_overlay_gate_not_closed",
    "second_pass_script_not_verified",
    "callback_or_polling_missing",
    "voice_ids_missing",
    "provider_media_urls_missing",
    "canon_reference_receipts_incomplete",
    "mode_cost_tier_ambiguity"
  ],
  "recommended_subagent": "persona-dream-panel-repair-gate"
}
```

Concrete examples from the run:

- Panel 1 was regenerated with a giant Chaos eye but lost Embry, so it must fail.
- Panel 4/5 showed the Chaos eye as a rectangular pasted overlay, so it must fail.
- Panel 9 was missing or visually de-emphasized required characters.
- The script lacked required realism details for important props and surfaces:
  steaming tea, umbrella fabric behavior, stone railing weathering/contact,
  baby Tyranid claw motion/speed/sound, wind/temperature/weather response, and
  human skin/face realism.
- Voices are still clone candidates only; no Kling provider `voice_id` exists.
- The provider packet must default to 720p/std for this experimental skill, not
  4K.
- Live provider execution remains blocked until all panel, voice, callback, URL,
  schema, and cost gates pass.

## Implemented Change Under Review

Added:

```text
agents/persona-dream-panel-repair-gate/AGENTS.md
```

This is a worker/subagent contract that owns second-pass script/image repair for
one storyboard panel at a time. It composes:

```text
persona-dream
best-practices-script-writer
best-practices-self-improvement-loop
best-practices-kling-scene
best-practices-kling-contact-sheet
memory
brave-search
casting-agent
contact-sheet
create-storyboard
create-image
scillm
```

The contract requires:

- a per-panel requirement matrix;
- pre-generation script coverage;
- source-reference sufficiency checks using human/project references, memory,
  then Brave Search for missing canon-sensitive references;
- corrective `scillm` image generation through receipt wrappers;
- post-generation visual review;
- no pasted overlay/composite acceptance;
- exact stop conditions;
- explicit provider-boundary rules.

Existing `skills/persona-dream/SKILL.md` has also been updated to require:

- a panel continuity and self-repair gate;
- a second-pass script/image check after every generated panel;
- strict failure for missing characters, unexplained visible elements, static
  highlighted props, missing movement/sound details, and pasted overlays;
- provider final gate checks for panel pass states, 720p/std default, stable
  `external_task_id`, callback or polling plan, provider media URLs, provider
  voice IDs, and cost estimates.

## Decision Requested

Is this subagent contract and associated skill gate specific enough to prevent
the observed false-progress loop before the project agent proceeds to regenerate
panels and repair the Kling dry-run packet?

## Required Reviewer Focus

Please review for:

- correctness of the subagent boundary;
- missing required inputs or outputs;
- whether the contract enforces script realism before image generation;
- whether it enforces post-generation visual verification from the actual image;
- whether it correctly handles persona-agnostic dream generation rather than
  hardcoding Horus/Embry;
- whether it prevents pasted overlays and report-only repairs;
- whether provider readiness is blocked until Kling-specific gates pass;
- whether the contract includes enough receipts for the orchestrating project
  agent and human to debug without ambiguity;
- whether any status labels are misleading or allow false readiness.

## Non-Goals

- Do not review the whole dirty repository.
- Do not propose running a live paid Kling call.
- Do not accept WebGPT review as final closure proof; deterministic local
  artifacts still need to pass after code review.
- Do not require a full implementation of the repair runner in this round unless
  the contract is unsafe without it.

## Prior Reviewer Critique To Re-Check

- A dedicated subagent is recommended and should own per-panel repair.
- Panel 1 failed because Embry is missing.
- Pasted overlay acceptance must be impossible.
- Unreviewed panels must block provider packets.
- Voice candidates without provider voice IDs must block live voiced calls.
- Stale 4K defaults must not remain in the provider path.
- callback/polling and provider-accessible media URLs must be part of the final
  provider gate.

## Expected Verdict Format

Return:

```json
{
  "verdict": "satisfied|needs_changes|blocked|insufficient_evidence",
  "blocking_findings": [
    {
      "file": "path",
      "issue": "specific problem",
      "why_it_matters": "risk",
      "required_change": "exact repair"
    }
  ],
  "non_blocking_findings": [],
  "patch_suggestions": [],
  "tests_to_run": [],
  "do_not_do": [],
  "aggregation_ready": false,
  "missing_evidence": []
}
```

Use `satisfied` only if the reviewed contract is adequate for the next phase:
using the subagent contract to repair the blocked panel/storyboard artifacts.
