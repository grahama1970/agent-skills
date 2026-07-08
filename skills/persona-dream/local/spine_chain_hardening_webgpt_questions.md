# WebGPT Clarifying Questions: Persona Dream 01/02/06/07 Chain Hardening

Sentinel: PERSONA_DREAM_SPINE_CHAIN_HARDENING_QUESTIONS_20260708

## Objective

Restart the Persona Dream prompt-contract hardening loop with WebGPT first.
The current local deterministic rung is accepted for fixture-level validators.
The next goal is to harden the actual chain across:

```text
01 Idea / Memory Residue
-> 02 Story
-> 06 Script
-> 07 Storyboard panel prompt
```

Do not answer as a high-level architecture note. Please close ambiguities enough
that a project agent can implement the next rung without inventing schema or
prompt-contract policy locally.

## Current Accepted Rung

The local implementation already has deterministic validators and fixtures for:

- `persona_dream.phase01.memory_residue_contract.v1`
- `persona_dream.phase02.story_contract_prompt.v1`
- `persona_dream.phase06.script_prompt_contract.v1`
- `persona_dream.phase07.panel_prompt_contract.v2`

Current accepted local claim:

```text
The Persona Dream spine has deterministic local prompt-contract validators for
01, 02, 06, and 07; positive fixtures pass, negative fixtures fail closed,
fixture SHA references are real and checked, and Tau proved the aggregate
checker locally with no live provider call.
```

Current proof boundary:

```text
provider_live=false
mocked=false
live_image_call_started=false
does not prove live memory recall/write
does not prove story/script creative quality
does not prove provider reference attachment
does not prove image generation or visual identity pass
does not prove storyboard panel generation time
does not prove final storyboard approval
```

## Known Next Rung From Prior WebGPT Review

Prior WebGPT response said the next smallest rung is:

```text
Persona Dream spine contract chain validator
```

Expected status:

```text
PASS_SPINE_CHAIN_CONTRACT_GATE
```

Expected blocker examples:

```text
BLOCKED_INTER_CONTRACT_HASH_MISMATCH
BLOCKED_MISSING_UPSTREAM_CONTRACT
BLOCKED_UNVALIDATED_UPSTREAM_CONTRACT
BLOCKED_COMPILED_PROMPT_HASH_MISSING
```

## Clarifying Questions To Close Before Implementation

1. What exact schema name should the chain artifact/receipt use?
2. What exact input shape should the chain validator consume?
   Should it accept:
   - a single chain manifest, or
   - separate `--phase01`, `--phase02`, `--phase06`, `--phase07` paths?
3. What exact fields must be added to phase 02, 06, and 07 contracts for
   upstream path/hash binding?
4. Should phase 07 bind to one phase 06 script contract, one compiled prompt
   file per panel/frame, or both?
5. What is the minimum compiled-prompt hash proof shape?
6. How should reviewer `PASS_*` precondition proof be represented?
   Should the chain validator require reviewer verdict files, validator receipt
   files, or both?
7. What good fixture chain should be built for this rung?
8. What negative fixture chains are mandatory?
9. Should the chain validator fail if upstream contracts pass standalone but
   downstream uses raw source text or serialized JSON?
10. What exact Tau DAG route should gate this rung?

## Requested Output Format

Please answer with:

```text
VERDICT: ACCEPTED | REVISE | BLOCKED
IMPLEMENTATION_ORDER:
SCHEMAS:
REQUIRED_FIELDS:
BLOCKER_STATUSES:
GOOD_FIXTURE:
NEGATIVE_FIXTURES:
VALIDATOR_COMMANDS:
TAU_DAG_ROUTE:
NON_CLAIMS:
STOP_CONDITION:
```

If any ambiguity remains, ask the next clarifying question explicitly instead
of assuming.
