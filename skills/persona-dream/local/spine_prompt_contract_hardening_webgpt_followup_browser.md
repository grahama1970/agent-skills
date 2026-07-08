# WebGPT Follow-Up Review Request: Persona Dream Spine Prompt-Contract Hardening

Sentinel: PERSONA_DREAM_SPINE_PROMPT_HARDENING_WEBGPT_FOLLOWUP_20260708

## Objective

Review the implemented Persona Dream creator/reviewer prompt-contract hardening
for phases:

- 01 Idea / Memory Residue
- 02 Story
- 06 Script
- 07 Storyboard panel prompt

This is a post-implementation reviewer pass. The local agent stopped after Tau
proof instead of returning the hardened result to WebGPT. Please review the
implementation shape, proof boundary, and remaining gaps.

## Implemented Components

Shared validator:

- `spine_prompt_contract_validation.py`

Phase validators:

- `validate_phase01_memory_residue_contract.py`
- `validate_phase02_story_contract_prompt.py`
- `validate_phase06_script_prompt_contract.py`
- `validate_phase07_prompt_contract.py`

Aggregate checker and Tau gate:

- `check_spine_prompt_contract_validators.py`
- `spine_prompt_contract_validator_tau_dag.json`
- `spine_prompt_contract_hardening_report.md`

## Important Correction Already Made

The first local implementation used placeholder-looking values such as
`sha256:777777...` in fixtures. That was wrong. It was corrected.

Current behavior:

- Fixture `sha256` fields bind to concrete local fixture files.
- The shared validator rejects malformed SHA-256 strings.
- The shared validator rejects local `path` + `sha256` mismatches.
- A malformed-SHA scan over the touched fixtures and DAG files returned
  `bad_sha_count 0`.

## Local Proof Summary

Direct aggregate checker result:

```text
status=PASS_SPINE_CONTRACT_GATE
live=true
mocked=false
provider_live=false
live_image_call_started=false
blockers=[]
```

Tau DAG result:

```text
schema=tau.dag_receipt.v1
status=PASS
verdict=PASS
ok=true
live=true
mocked=false
provider_live=false
selected_agents=["spine-prompt-contract-validator"]
```

Aggregate node receipt result:

```text
schema=persona_dream.spine_prompt_contract_validator_receipt.v1
status=PASS_SPINE_CONTRACT_GATE
blockers=[]
live=true
mocked=false
provider_live=false
live_image_call_started=false
```

Additional checks:

```text
python3 -m py_compile ... -> passed
python3 scripts/check_mock_evidence_claims.py -> passed
malformed SHA scan -> bad_sha_count 0
```

## Fixture Outcomes

Positive:

- 01 good -> `PASS_MEMORY_RESIDUE_CONTRACT`
- 02 good -> `PASS_STORY_CONTRACT`
- 06 good -> `PASS_SCRIPT_CONTRACT`
- 07 good -> `PASS_PROMPT_CONTRACT`

Negative:

- 01 serialized memory JSON text -> `BLOCKED_SERIALIZED_MEMORY_TEXT`
- 02 serialized source/story JSON blob -> `BLOCKED_STORY_CONTRACT`
- 06 loose asset usage / serialized script -> `BLOCKED_SCRIPT_CONTRACT`
- 07 Kai spatially implied while required -> `BLOCKED_PROMPT_CONTRACT`

High-signal blockers observed:

- `serialized_json_blob_in_prompt_text:source_residue[0].text`
- `serialized_json_blob_in_prompt_text:typed_source_context.source_context`
- `loose_asset_usage:Embry`
- `required_identity_spatially_implied:Kai`

## Current Proof Boundary

This proves:

- Deterministic positive fixtures pass.
- Deterministic negative fixtures fail closed.
- Local hashed fixture references are checked for SHA-256 match.
- Tau ran the aggregate checker through the local command-loop DAG runner.

This does not prove:

- Live memory recall/write quality.
- Story or script creative quality.
- Provider reference attachment.
- Image generation or visual identity pass.
- Storyboard panel generation time.
- Final storyboard approval.

## Questions For WebGPT

1. Did the implementation cover the relevant creator/reviewer prompt hardening
   loop for 01, 02, 06, and 07, or is any prompt contract stage still missing?
2. Are the validators still too permissive in any high-risk way?
3. Is the SHA correction sufficient for fixture-level proof, or should the next
   rung require hash validation for inter-contract inputs too?
4. What is the next smallest non-provider proof rung after this hardening?
5. Should this be considered ready to wire into the actual creator/reviewer DAG
   prompts, or should another validator/reviewer gate happen first?

Please answer with:

- `ACCEPTED`, `REVISE`, or `BLOCKED`
- concrete required changes if not accepted
- explicit non-claims to preserve
- the next smallest proof rung
