# WebGPT / create-architecture Request: Live Creator-Reviewer Hardening

Continue the Persona Dream `dreams` collaboration in the same ChatGPT conversation.

Exact tab binding:
- URL: `https://chatgpt.com/c/6a4c25f5-1460-83ea-83cc-e63ce7a497d9`
- tab id: `837358015`
- Desktop: 2

## Current State

The reusable 01/02/06/07 prompt-contract infrastructure is now locally hardened, but not yet enforced in the live creator/reviewer runtime.

Committed local chain gate:
- Commit: `fe0d8e03690a2b0214c99d64808a367209026370`
- Validator: `skills/persona-dream/scripts/validate_persona_dream_spine_chain.py`
- Aggregate checker: `skills/persona-dream/scripts/check_persona_dream_spine_chain.py`
- Good manifest: `skills/persona-dream/tests/fixtures/spine_chain/good/spine_chain_manifest.v1.json`
- Tau DAG: `skills/persona-dream/local/spine_chain_contract_validator_tau_dag.json`
- Tau receipt: `skills/persona-dream/local/persona-dream-spine-chain-contract-validator-run/dag-receipt.json`
- Chain receipt: `skills/persona-dream/local/persona-dream-spine-chain-contract-validator-run/command-loop/command-artifacts/command-loop-step-002/spine_chain_validator_receipt.v1.json`

Receipt facts:
- Tau DAG: `status=PASS`, `ok=true`, `live=true`, `mocked=false`, `provider_live=false`
- Chain validator: `status=PASS_SPINE_CHAIN_CONTRACT_GATE`, `blockers=[]`, `live_image_call_started=false`
- SHA scan: `bad_sha_count 0`

WebGPT hash convention already accepted:
- Phase 07 panel contracts do not embed compiled prompt proof.
- The chain manifest hashes contracts and compiled prompts as raw bytes.
- The manifest binds each compiled prompt to the full raw-byte hash of its source contract.

## Architecture Artifact

I created an architecture definition for this hardening stage:

`skills/persona-dream/local/live_creator_reviewer_hardening_architecture.yaml`

It shows:
- 01/02/06 typed contracts,
- spine chain manifest gate,
- Phase 07 prompt contracts,
- compiled prompt proofs,
- missing live preflight gate,
- panel creator,
- provider image call,
- panel reviewer,
- reviewer PASS precondition gate,
- Tau evidence boundary.

## Live Runtime File

Likely enforcement target:

`skills/persona-dream/scripts/phase07_storyboard_tau_node.py`

Current live behavior summary:
- `panel-creator` can call generation via `_ensure_storyboard_frame_artifacts(...)`.
- `_run_creator(...)` writes `storyboard_creator_receipt.json`, `storyboard_panel_manifest.json`, and frame generation receipts.
- `_run_reviewer(...)` promotes reviewer-accepted frames, validates the storyboard packet, and writes `storyboard_review_verdict.json`.
- The new spine chain manifest gate is not yet a hard preflight for provider image calls or reviewer PASS claims.

## Request

Use the architecture above to specify the next hardening patch. Do not give generic prompt advice.

Answer with an implementable design:

1. Exact live-enforcement invariant:
   What must be true before `panel-creator` can start any provider image call?

2. Exact inputs:
   Should live enforcement consume:
   - the existing chain manifest,
   - a run-specific generated chain manifest,
   - per-panel prompt contracts plus compiled prompt proof sidecars,
   - or another artifact?

3. Exact patch location:
   Which functions in `phase07_storyboard_tau_node.py` should call the contract/chain validator before generation and before reviewer PASS?

4. Exact receipt schema:
   What receipt should be written when the live preflight passes or blocks?
   Include schema name, status names, required fields, and non-claims.

5. Exact fail-closed statuses:
   Include statuses for:
   - missing chain manifest,
   - stale compiled prompt hash,
   - provider call attempted before preflight PASS,
   - reviewer PASS without validator receipt,
   - targeted panel scope not represented in manifest.

6. Minimal deterministic fixtures/tests:
   Give the first smallest test rung to prove the live runtime refuses provider generation when the preflight is missing/stale.

7. Tau gate:
   Define the next local-only Tau DAG route and expected receipt fields.

Constraints:
- Do not start provider/image generation in this rung.
- Keep `provider_live=false`, `mocked=false`, `live_image_call_started=false`.
- Do not claim final storyboard approval.
- The result should be a patchable local enforcement design, not a new dashboard or report.

Return the implementation order and exact acceptance criteria.
