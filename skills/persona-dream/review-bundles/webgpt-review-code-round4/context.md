# Review Context Round 4: Persona-Dream Panel Repair Gate

## Objective

Round 3 WebGPT review returned `needs_changes`. This round asks whether the
remaining blockers are now repaired well enough to proceed to the next phase:
using the panel repair gate to repair blocked storyboard panels and the Kling
dry-run packet.

## Round 3 Blocking Findings

1. Provider voice source receipts were checked for existence/JSON only, not for
   matching `provider`, `voice_id`, and voice token evidence.
2. The JSON schema still diverged from the validator because required fields
   lacked property definitions/type constraints.

## Repairs Made

1. `skills/persona-dream/scripts/validate_panel_repair_gate.py`
   - Added `voice_source_matches`.
   - Under `--require-provider-eligible`, each provider voice source receipt
     must contain PASS/READY status or verdict, matching `provider`, matching
     `voice_id`, and matching `voice_token`.
   - Non-object top-level receipts now return structured JSON `FAIL` instead of
     an attribute error.

2. Voice fixtures
   - Updated `panel_repair_gate_artifacts/provider_voice_clone_receipt.json` to
     include `status: PASS`, `provider: kling`, `voice_id:
     voice_fixture_123`, and `voice_token: voice_1`.
   - Added `panel_repair_gate_valid_voiced.json`, which passes provider-eligible
     validation only with a matching provider voice receipt.
   - Added `panel_repair_gate_invalid_voice_source_mismatch.json`, which points
     at an existing valid JSON object that does not contain the matching
     provider voice proof and fails validation.

3. `skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json`
   - Added explicit property definitions for every required receipt/path field:
     `requirement_matrix`, `script_coverage_receipt`,
     `post_generation_script_coverage_receipt`, `reference_receipt`,
     `generation_receipt`, `visual_review_receipt`, `no_overlay_receipt`.
   - Added non-empty string definitions for `callback_or_polling_plan`,
     `external_task_id`, `cost_estimate`, and `provider_resolution`.
   - Added `minItems: 1` for `provider_media_urls`.
   - Added `minProperties: 1` for `media_hashes`.

4. `skills/persona-dream/scripts/check_panel_repair_gate_schema_consistency.py`
   - Now fails if any required schema field lacks a property definition.
   - Now checks required string fields have `type: string` and `minLength >= 1`.
   - Now checks required array/object fields have the expected constraints.

## Local Verification

Command:

```bash
bash skills/persona-dream/sanity.sh
```

Result:

- Overall command exited 0.
- Valid silent fixture passed.
- Valid voiced fixture passed.
- Invalid partial-pass fixture failed.
- Invalid provider-fields fixture failed.
- Invalid provider-voice-ID-claim fixture failed.
- Invalid missing-receipts fixture failed.
- Invalid voice source mismatch fixture failed with:
  - `voice source receipt provider does not match claimed provider`
  - `voice source receipt voice_id does not match claimed voice_id`
  - `voice source receipt voice_token does not match claimed token`
- Schema consistency check passed.

## Decision Requested

Are the round-3 blocking findings now repaired well enough to proceed to the
next phase: using this gate to repair the current blocked storyboard/panel
artifacts?

Return `satisfied` only for that next repair phase. Do not approve live Kling
execution.
