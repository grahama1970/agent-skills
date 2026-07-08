Choose C.

The Phase 07 panel contract should not embed the compiled prompt proof. The compiled prompt proof lives only in the spine chain manifest entry, where it can hash the full panel contract file normally without self-reference.

Clarification

Use this convention:

Panel prompt contract file:
  phase07/prompt_contracts/sb_004.start_frame.attempt_001.json

Compiled prompt file:
  phase07/prompts/sb_004.start_frame.attempt_001.md

Chain manifest:
  records both files and binds:
    compiled_prompt.derived_from_contract_sha256 == sha256(full panel prompt contract file bytes)

Do not use projection hashing for this rung. No “exclude compiled_prompt” rule. No canonical self-hash rule. No embedded compiled_prompt.derived_from_contract_sha256 inside the contract itself.

This avoids ambiguity and keeps the proof easy to recompute locally.

Required schema change

Remove this block from every Phase 07 panel/frame contract:

JSON
"compiled_prompt": {
  "schema": "persona_dream.phase07.compiled_prompt_proof.v1",
  "path": "...",
  "sha256": "sha256:...",
  "derived_from_contract_path": "...",
  "derived_from_contract_sha256": "sha256:...",
  "renderer": {
    "name": "phase07_prompt_renderer",
    "version": "v1",
    "deterministic": true
  },
  "render_mode": "deterministic",
  "may_be_hand_edited": false
}

Keep the Phase 07 panel contract focused on the prompt contract itself:

JSON
{
  "schema": "persona_dream.phase07.panel_prompt_contract.v2",
  "panel_id": "sb_004",
  "frame_id": "sb_004.start_frame",
  "attempt": 1,
  "input_contracts": {
    "phase06_script_prompt_contract": {
      "path": "phase06/good_script_prompt_contract.json",
      "sha256": "sha256:...",
      "validator_receipt_path": "phase06/validate_script_contract_receipt.json",
      "validator_receipt_sha256": "sha256:...",
      "required_validator_status": "PASS_SCRIPT_CONTRACT"
    }
  },
  "generation_scope": {},
  "model_policy": {},
  "required_identities": [],
  "identity_requirements": {},
  "identity_reference_assets": {},
  "temporal_continuity_reference_assets": {},
  "camera_contract": {},
  "environment_requirements": {},
  "story_action": {},
  "prompt_sections": {},
  "provider_request_shape": {}
}

The compiled prompt proof belongs in the chain manifest.

Updated chain manifest Phase 07 entry

Each Phase 07 panel/frame entry should use this shape:

JSON
{
  "panel_id": "sb_004",
  "frame_id": "sb_004.start_frame",
  "contract_path": "phase07/prompt_contracts/sb_004.start_frame.attempt_001.json",
  "contract_sha256": "sha256:<sha256 of full contract file bytes>",
  "validator_receipt_path": "phase07/receipts/prompt_validation/sb_004.start_frame.attempt_001.json",
  "validator_receipt_sha256": "sha256:<sha256 of validator receipt file bytes>",
  "required_validator_status": "PASS_PROMPT_CONTRACT",
  "compiled_prompt": {
    "schema": "persona_dream.phase07.compiled_prompt_proof.v1",
    "path": "phase07/prompts/sb_004.start_frame.attempt_001.md",
    "sha256": "sha256:<sha256 of compiled prompt markdown file bytes>",
    "derived_from_contract_path": "phase07/prompt_contracts/sb_004.start_frame.attempt_001.json",
    "derived_from_contract_sha256": "sha256:<same value as contract_sha256>",
    "renderer": {
      "name": "phase07_prompt_renderer",
      "version": "v1",
      "deterministic": true
    },
    "render_mode": "deterministic",
    "may_be_hand_edited": false
  }
}
Exact hash convention

For this rung, every sha256 value is:

"sha256:" + SHA256(raw file bytes)

Rules:

1. Do not canonicalize JSON.
2. Do not remove fields before hashing.
3. Do not hash a projection.
4. Do not normalize whitespace.
5. Do not normalize line endings.
6. Hash the exact bytes present on disk.

This applies to:

contract_sha256
validator_receipt_sha256
compiled_prompt.sha256
compiled_prompt.derived_from_contract_sha256
upstream contract sha256 values

The validator should read each file as bytes and recompute SHA-256 directly.

Exact validation rules

For each Phase 07 panel_prompt_contracts[] entry in the manifest:

1. contract_path exists.
2. contract_sha256 is a well-formed sha256:<64 lowercase hex chars>.
3. sha256(raw bytes of contract_path) == contract_sha256.
4. contract JSON schema == persona_dream.phase07.panel_prompt_contract.v2.
5. contract must not contain top-level compiled_prompt.
6. validator_receipt_path exists.
7. validator_receipt_sha256 is well formed.
8. sha256(raw bytes of validator_receipt_path) == validator_receipt_sha256.
9. validator receipt status == required_validator_status.
10. compiled_prompt exists in manifest entry.
11. compiled_prompt.schema == persona_dream.phase07.compiled_prompt_proof.v1.
12. compiled_prompt.path exists.
13. compiled_prompt.sha256 is well formed.
14. sha256(raw bytes of compiled_prompt.path) == compiled_prompt.sha256.
15. compiled_prompt.derived_from_contract_path == contract_path.
16. compiled_prompt.derived_from_contract_sha256 == contract_sha256.
17. compiled_prompt.renderer.deterministic == true.
18. compiled_prompt.render_mode == "deterministic".
19. compiled_prompt.may_be_hand_edited == false.

Fail if any Phase 07 contract embeds the compiled prompt proof:

BLOCKED_COMPILED_PROMPT_PROOF_EMBEDDED_IN_CONTRACT

Fail if the manifest compiled prompt points to a different source contract:

BLOCKED_COMPILED_PROMPT_CONTRACT_PATH_MISMATCH

Fail if the compiled prompt proof uses a different contract hash:

BLOCKED_COMPILED_PROMPT_CONTRACT_HASH_MISMATCH

Fail if the compiled prompt file hash is missing or wrong:

BLOCKED_COMPILED_PROMPT_HASH_MISSING
BLOCKED_COMPILED_PROMPT_HASH_MISMATCH

Fail if the prompt is marked hand-editable:

BLOCKED_COMPILED_PROMPT_HAND_EDITABLE
Necessary changes to previous requirements

Replace the prior requirement:

Add compiled_prompt block to every Phase 07 panel/frame contract.

with:

Add compiled_prompt proof to every Phase 07 panel/frame entry in the chain manifest.

Keep the requirement:

The good fixture must contain all eight Phase 07 start/end prompt contracts.

But now each of the eight entries must have a corresponding manifest-level compiled_prompt proof.

Updated negative fixtures

Keep the prior negative fixtures, but adjust names/expectations slightly:

bad_chain_compiled_prompt_hash_missing.json
  -> BLOCKED_COMPILED_PROMPT_HASH_MISSING

bad_chain_compiled_prompt_hash_mismatch.json
  -> BLOCKED_COMPILED_PROMPT_HASH_MISMATCH

bad_chain_compiled_prompt_contract_hash_mismatch.json
  -> BLOCKED_COMPILED_PROMPT_CONTRACT_HASH_MISMATCH

bad_chain_compiled_prompt_contract_path_mismatch.json
  -> BLOCKED_COMPILED_PROMPT_CONTRACT_PATH_MISMATCH

bad_chain_compiled_prompt_embedded_in_contract.json
  -> BLOCKED_COMPILED_PROMPT_PROOF_EMBEDDED_IN_CONTRACT
Final convention

Use this as the implementation rule:

Contracts do not hash themselves.
The manifest hashes contracts.
The manifest hashes compiled prompts.
The manifest binds each compiled prompt to the full raw-byte hash of its source contract.

That is the deterministic, non-self-referential convention for this rung.
