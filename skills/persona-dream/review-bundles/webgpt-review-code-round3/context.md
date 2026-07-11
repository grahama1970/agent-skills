# Review Context Round 3: Persona-Dream Panel Repair Gate

## Objective

Round 2 WebGPT review returned `needs_changes`. This round asks whether the
remaining blockers were repaired well enough to use the panel repair gate as the
next phase controller.

## Round 2 Blocking Findings

1. Provider voice readiness could be asserted without concrete provider
   `voice_id` evidence.
2. Receipt path fields were non-empty strings only; missing or unparseable
   receipt files could still pass.
3. The JSON schema was weaker than the validator and omitted provider-readiness
   fields.

## Repairs Made

1. `skills/persona-dream/scripts/validate_panel_repair_gate.py`
   - Added `provider_voice_ids` validation.
   - Requires `voice_id_status=SILENT_SCENE` or concrete provider voice IDs.
   - When `voice_id_status=PROVIDER_VOICE_ID_READY`, each voice token must have
     `provider`, `voice_id`, and `source_receipt`.
   - Under `--require-provider-eligible`, resolves receipt paths relative to the
     panel receipt path or `--artifact-root`.
   - Requires required receipts to exist, parse as JSON objects, and contain
     matching PASS evidence for script coverage, post-generation script
     coverage, reference evidence, visual review, and no-overlay review.
   - `--require-provider-eligible` now also requires `provider_eligibility=true`.

2. `skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json`
   - Added required `provider_media_urls`, `media_hashes`,
     `callback_or_polling_plan`, `cost_estimate`, and `provider_voice_ids`.
   - Added `provider_voice_ids` object shape with `provider`, `voice_id`, and
     `source_receipt`.

3. `agents/persona-dream-panel-repair-gate/AGENTS.md`
   - Added `provider_voice_ids` to required output.
   - Provider boundary now says every voice token must have concrete provider
     `voice_id` evidence and a source receipt, unless the scene is silent.

4. New deterministic fixtures/checks
   - Real valid fixture receipt artifacts under:
     `skills/persona-dream/scripts/fixtures/panel_repair_gate_artifacts/`
   - `panel_repair_gate_invalid_voice_id_claim.json`
   - `panel_repair_gate_invalid_missing_receipts.json`
   - `check_panel_repair_gate_schema_consistency.py`

## Local Verification

Command:

```bash
bash skills/persona-dream/sanity.sh
```

Result:

- Overall command exited 0.
- Valid panel gate fixture passed.
- Invalid partial-pass fixture failed.
- Invalid provider-field fixture failed.
- Invalid voiced-provider claim failed with:
  `provider_voice_ids is required when voice_id_status=PROVIDER_VOICE_ID_READY`.
- Invalid missing-receipts fixture failed with explicit missing receipt paths.
- Schema consistency check passed.

## Decision Requested

Are the round-2 blocking findings now repaired well enough to proceed to the
next phase: using the panel repair gate to repair blocked storyboard panels and
the Kling dry-run packet?

Return `satisfied` only for that next repair phase. Do not approve live Kling
execution.
