# Persona Dream End-to-End Pipeline P0 Spine

## Goal

This patch adds a deterministic P0 pipeline spine for persona-dream runs. The spine is receipt-backed, schema-validated, and fail-closed at the paid provider boundary. It proves that an end-to-end run root can be classified without making live provider calls or producing final creative assets.

## Non-goals

The P0 spine does not submit live Kling jobs, charge a paid account, generate final video/image assets, or replace the legacy storyboard-first fixture flow. Live submission remains blocked unless a future patch supplies a live approval path, credentials, and provider evidence that are all validated together.

## Compatibility note: legacy paid-call schema

This corrected bundle intentionally does **not** add, overwrite, or otherwise modify `schemas/paid_call_approval_receipt.schema.json`.

That path is reserved for the repository's legacy paid-call approval contract used by `scripts/storyboard_first_fixture.py` and the legacy pipeline documentation. The P0 spine uses a new schema path instead:

```text
schemas/pipeline_paid_call_approval_receipt.schema.json
```

All P0 fixtures, validator references, tests, and manifest entries point to the new P0-specific schema path. This keeps the legacy approval schema semantically compatible while still allowing the P0 pipeline to prove paid-call gating behavior.

## System boundary

The P0 spine classifies a local run root. A run root contains:

- `run_manifest.json` describing mode, required inputs, ordered stages, and schema references.
- `receipts/stage_receipt.json` capturing input completeness.
- `receipts/pipeline_paid_call_approval_receipt.json` capturing explicit paid-call authorization state.
- `receipts/provider_readiness_receipt.json` capturing provider readiness evidence.
- `receipts/kling_submit_gate_receipt.json` capturing the terminal Kling submit gate decision.
- `receipts/pipeline_terminal_report.json` capturing the final classifier status.

The validator performs only local file reads and schema checks. It does not contact Kling or any other provider.

## State machine

The spine has three externally meaningful outcomes in P0:

1. `PASS`: every local receipt is well formed and no terminal blocker is present. P0 fixtures do not exercise this as a live-ready path.
2. `BLOCKED_MISSING_INPUT`: required local inputs are absent or explicitly incomplete.
3. `DRY_RUN_NOT_LIVE_SUBMITTABLE`: provider readiness is satisfied only for dry-run mode, paid-call approval is not live-approved, and the Kling gate correctly refuses live submission.

The terminal status is derived fail-closed. Missing required receipts, missing required inputs, malformed schemas, and inconsistent provider evidence all prevent `PASS`.

## Paid provider gate

The paid-call gate requires an explicit receipt that says whether live paid submission is approved. In this P0 patch, live submission is never performed. The provider-ready dry-run fixture demonstrates the intended terminal behavior: the provider readiness receipt can be complete, but the Kling submit gate still returns `DRY_RUN_NOT_LIVE_SUBMITTABLE` because the run is a dry-run and `live_submission_allowed` is false.

## Evidence requirements

A provider-ready dry-run must include:

- `provider_readiness_receipt.provider == "kling"`.
- `provider_readiness_receipt.ready_for_dry_run == true`.
- `pipeline_paid_call_approval_receipt.live_submission_allowed == false`.
- `kling_submit_gate_receipt.decision == "DRY_RUN_NOT_LIVE_SUBMITTABLE"`.

A blocked missing-input run must include:

- `stage_receipt.inputs_complete == false`.
- at least one missing input name.
- terminal status `BLOCKED_MISSING_INPUT`.

## Implementation overview

`scripts/validate_pipeline_spine.py` loads a run root, validates every declared receipt against the schemas, checks that the P0 paid-call schema path is used, and derives the terminal status from receipt evidence. The test suite covers manifest integrity, schema parseability, the two required fixture outcomes, and six schema-validation subtests.
