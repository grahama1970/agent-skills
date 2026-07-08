SENTINEL: persona-dream-spine-chain-hash-convention-followup-20260708T0206

You are WebGPT/create-architecture for Persona Dream. Continue the prior accepted guidance for the 01->02->06->07 spine chain hardening rung.

Need a precise clarification before implementation.

Prior guidance required adding this block to every Phase 07 panel/frame contract:

{
  "compiled_prompt": {
    "schema": "persona_dream.phase07.compiled_prompt_proof.v1",
    "path": "phase07/prompts/sb_004.start_frame.attempt_001.md",
    "sha256": "sha256:...",
    "derived_from_contract_path": "phase07/prompt_contracts/sb_004.start_frame.attempt_001.json",
    "derived_from_contract_sha256": "sha256:...",
    "renderer": {"name":"phase07_prompt_renderer","version":"v1","deterministic":true},
    "render_mode": "deterministic",
    "may_be_hand_edited": false
  }
}

But if this block is embedded inside the same Phase 07 panel prompt contract JSON, then `derived_from_contract_sha256` appears to be self-referential: changing the field changes the contract hash it claims to equal.

Question: What exact deterministic convention should the validator implement?

Please choose one and specify exact validation rules:

A. The Phase 07 panel contract embeds `compiled_prompt`, but `derived_from_contract_sha256` is the SHA-256 of a canonical contract projection excluding `compiled_prompt.derived_from_contract_sha256` only.

B. The Phase 07 panel contract embeds `compiled_prompt`, but `derived_from_contract_sha256` is the SHA-256 of a canonical contract projection excluding the whole `compiled_prompt` block.

C. The Phase 07 panel contract should not embed the compiled prompt proof. Instead, compiled prompt proof lives only in the chain manifest entry, where it can hash the full panel contract file normally.

D. Other: give exact schema and hash validation rule.

Constraints:
- User explicitly rejected hallucinated/placeholder SHA-256 values.
- The fixture must contain real SHA-256 values that the validator recomputes locally.
- Keep the prior requirement: one manifest input, good fixture with all eight Phase 07 start/end prompt contracts, mandatory negative manifests, local Tau gate only, provider_live=false, mocked=false, live_image_call_started=false.

Return only the clarification plus any necessary changes to the previous schema/validator requirements.
