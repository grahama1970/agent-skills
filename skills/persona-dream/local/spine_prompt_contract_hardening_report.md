# Persona Dream Spine Prompt-Contract Hardening

Generated: 2026-07-08

## Scope

This hardens deterministic creator/reviewer prompt-contract gates for:

- 01 Idea / Memory Residue
- 02 Story
- 06 Script
- 07 Storyboard panel prompts

The hardening is local-only and pre-provider. It does not call image generation,
memory DBs, or paid providers.

## Validators

- `skills/persona-dream/scripts/validate_phase01_memory_residue_contract.py`
- `skills/persona-dream/scripts/validate_phase02_story_contract_prompt.py`
- `skills/persona-dream/scripts/validate_phase06_script_prompt_contract.py`
- `skills/persona-dream/scripts/validate_phase07_prompt_contract.py`
- Shared validation helpers: `skills/persona-dream/scripts/spine_prompt_contract_validation.py`
- Aggregate Tau checker: `skills/persona-dream/scripts/check_spine_prompt_contract_validators.py`

## Fixture Outcomes

Positive fixtures:

- `phase01/good_memory_residue_contract.json` -> `PASS_MEMORY_RESIDUE_CONTRACT`
- `phase02/good_story_contract_prompt.json` -> `PASS_STORY_CONTRACT`
- `phase06/good_script_prompt_contract.json` -> `PASS_SCRIPT_CONTRACT`
- `phase07/good_panel_prompt_contract_sb004.json` -> `PASS_PROMPT_CONTRACT`

Negative fixtures:

- `phase01/bad_memory_residue_serialized_json_text.json` -> `BLOCKED_SERIALIZED_MEMORY_TEXT`
- `phase02/bad_story_contract_serialized_memory_blob.json` -> `BLOCKED_STORY_CONTRACT`
- `phase06/bad_script_contract_loose_asset_usage.json` -> `BLOCKED_SCRIPT_CONTRACT`
- `phase07/bad_prompt_contract_kai_spatially_implied.json` -> `BLOCKED_PROMPT_CONTRACT`

Expected high-signal blockers include:

- `serialized_json_blob_in_prompt_text:source_residue[0].text`
- `serialized_json_blob_in_prompt_text:typed_source_context.source_context`
- `loose_asset_usage:Embry`
- `required_identity_spatially_implied:Kai`

## SHA Discipline

Fixture `sha256` fields now bind to concrete local fixture files under:

```text
skills/persona-dream/tests/fixtures/assets/
```

The validators reject malformed SHA-256 strings and hash mismatches for local
fixture paths. Placeholder-looking `sha256:777...` values were removed.

## Tau Gate

- DAG: `skills/persona-dream/local/spine_prompt_contract_validator_tau_dag.json`
- Command spec: `skills/persona-dream/local/spine_prompt_contract_validator_tau_command.json`
- DAG receipt: `/mnt/storage12tb/persona-dream/spine-prompt-contract-validator-20260708T0107/tau-spine-contract-gate/dag-receipt.json`
- Aggregate node receipt: `/mnt/storage12tb/persona-dream/spine-prompt-contract-validator-20260708T0107/tau-spine-contract-gate/command-loop/command-artifacts/command-loop-step-001/spine_prompt_contract_validator_receipt.json`

Tau result:

```text
status=PASS
verdict=PASS
live=true
mocked=false
provider_live=false
```

## Proof Boundary

Proves:

- The four positive prompt-contract fixtures pass deterministic local validators.
- The four negative prompt-contract fixtures fail closed with expected blockers.
- Local fixture references with `sha256` are checked against actual file hashes.
- Tau ran the aggregate checker through the local command-loop DAG runner.

Does not prove:

- Live memory recall or write quality.
- Story or script creative quality.
- Provider reference attachment.
- Image generation or visual identity pass.
- Storyboard panel generation time.
- Final storyboard approval.
