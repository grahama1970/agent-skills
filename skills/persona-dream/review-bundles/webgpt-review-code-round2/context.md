# Review Context Round 2: Persona-Dream Panel Repair Gate

## Objective

Round 1 WebGPT review returned `needs_changes`. This round asks whether the
blocking findings were repaired well enough to use the subagent contract and
validator as the next controlling gate for panel regeneration and Kling
preflight repair.

## Round 1 Blocking Findings

1. `agents/casting-agent/AGENTS.md` hardcoded Horus/Embry/Tyranids package keys.
2. `agents/persona-dream-panel-repair-gate/AGENTS.md` mixed intermediate pass
   statuses with final acceptance statuses.
3. The panel gate lacked a distinct post-generation script/realism receipt.
4. The gate was prose-only and lacked deterministic schema/validator coverage.

## Repairs Made

1. `agents/casting-agent/AGENTS.md`
   - Replaced hardcoded `characters.horus`, `characters.embry`,
     `creatures.tyranids`, and prop keys with generic entity-key patterns:
     `characters.<character_id>`, `creatures.<creature_id>`,
     `scenery.<environment_id>`, `props.<prop_id>`, `objects.<object_id>`,
     and `vehicles.<vehicle_id>`.
   - Explicitly states that Horus/Embry/Tyranids keys are fixture examples only.

2. `agents/persona-dream-panel-repair-gate/AGENTS.md`
   - Replaced partial final pass states with one normal final pass:
     `PASS_PANEL_REVIEWED`.
   - Moved script/reference/visual/no-overlay/provider checks into explicit
     subgate fields.
   - Added `post_generation_script_coverage_receipt.json`.
   - Added required provider fields: URLs, hashes, mode, resolution, callback or
     polling plan, external task ID, voice ID status, cost estimate, and provider
     packet status.
   - States that `provider_eligibility` stays false unless final status is
     `PASS_PANEL_REVIEWED` and every required subgate/provider field passes.

3. `skills/persona-dream/SKILL.md`
   - Added the validator command to the panel continuity/self-repair gate.
   - Clarified that `PASS_SCRIPT_COVERAGE`, `PASS_REFERENCE_EVIDENCE`, and
     `PASS_VISUAL_REVIEW` are rejected as final panel statuses.

4. New deterministic gate artifacts
   - `skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json`
   - `skills/persona-dream/scripts/validate_panel_repair_gate.py`
   - `skills/persona-dream/scripts/fixtures/panel_repair_gate_valid.json`
   - `skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_partial_pass.json`
   - `skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_provider_fields.json`

## Local Verification

Command:

```bash
bash skills/persona-dream/sanity.sh
```

Result:

- Static dream sanity: `status: ok`.
- Video-plan sanity: `status: ok`.
- Storyboard-first regression fixture: `status: ok`.
- `panel_repair_gate_valid.json` passed with `--require-provider-eligible`.
- `panel_repair_gate_invalid_partial_pass.json` failed as expected, including:
  - `PASS_SCRIPT_COVERAGE is an intermediate subgate, not a final panel status`
  - missing post-generation script coverage
  - missing visual/no-overlay receipts
  - missing provider URLs/hashes/callback/cost
- `panel_repair_gate_invalid_provider_fields.json` failed as expected, including:
  - non-std/720p default rejection
  - missing external task ID
  - missing callback/polling plan
  - local-only provider media URL
  - missing provider voice ID

## Decision Requested

Do these repairs satisfy the round-1 blocking review enough to proceed to the
next phase: using the panel repair gate to repair the current blocked
storyboard panels and Kling dry-run packet?

Return `needs_changes` if any blocking contract problem remains. Return
`satisfied` only if this gate is adequate for that next phase. This is not a
request to approve live Kling execution.
