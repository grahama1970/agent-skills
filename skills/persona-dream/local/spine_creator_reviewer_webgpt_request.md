# WebGPT Review Request: Persona Dream Spine Creator-Reviewer Prompt Contracts

Continue the Persona Dream prompt/DAG collaboration in the existing `dreams`
ChatGPT conversation.

Exact tab binding requested by the human:
- name: dreams
- URL: https://chatgpt.com/c/6a4c25f5-1460-83ea-83cc-e63ce7a497d9
- tab id: 837358015
- Desktop: 2

## Goal

Optimize the reusable creator-reviewer prompt contracts for the Persona Dream
pipeline spine:

1. `01 Idea / Memory Residue`
2. `02 Story`
3. `06 Script`
4. `07 Storyboard`

Do not optimize per-dream instance content. Optimize reusable contracts,
validators, invalid fixtures, and Tau gates that future dreams can instantiate
with new idea/cast/assets/settings/timing.

## Evidence We Already Have

### 07 Storyboard

Known problem:
- The final four-panel storyboard passed Tau, but `sb004` took roughly 13
  minutes due to a repair loop.
- The root cause was prompt/adapter weakness: identity and continuity constraints
  were not deterministic enough before live image generation.
- Tau correctly caught defects, but Tau should not be the main mechanism for
  making vague creator prompts usable.

Prior WebGPT decision:
- First implementation rung is `A`: prompt contract JSON plus deterministic
  validator only, no live generation changes yet.
- Invariant: no live image call may start until the per-frame prompt contract
  proves required identities, reference attachments, camera feasibility,
  continuity references, negative constraints, and generation scope.
- Bad fixture: `Kai required + spatially implied` must fail before generation.

Tau gate already checked that the WebGPT ambiguity decision was closed:
- `skills/persona-dream/local/phase07_prompt_dag_review_tau_dag.json`
- DAG receipt facts: `PASS`, `live:true`, `mocked:false`, `provider_live:false`,
  observed route `review-checker -> human`, no alerts.

### 06 Script

Current artifacts:
- `skills/persona-dream/reports/pipeline-complete/phase_06_script/script_contract.json`
- `skills/persona-dream/reports/pipeline-complete/phase_06_script/script-reviewer-verdict.json`
- `skills/persona-dream/reports/pipeline-complete/phase_06_script/receipts/validate_script_contract.json`

Observed schema keys in `script_contract.json`:
- `script`
- `timed_beats`
- `timed_transcript`
- `action_blocks`
- `dialogue_blocks`
- `entity_environment_script_table`
- `asset_usage`
- `interaction_matrix_coverage`
- `realism_contract`
- `quality_checks`
- `source_context_summary`

Risk:
- If `06 Script` emits loose asset usage, ambiguous beats, serialized JSON text,
  or weak entity/action/timing fields, `07 Storyboard` inherits bad constraints.

### 02 Story

Known issue from current UI/pipeline behavior:
- Text memories can arrive as serialized JSON strings.
- We just fixed the `01 Idea` UI display layer to JSON-extract fields like
  `story`, `asset_usage`, `visual_consistency_note`, `description`, and `title`
  before rendering.
- That UI fix prevents raw display leakage, but the reusable prompt contract
  still needs to require structured extraction instead of passing serialized
  memory blobs downstream as prompt text.

Risk:
- If `02 Story` accepts or emits serialized JSON text instead of typed fields,
  `06 Script` receives muddy source context and `07 Storyboard` receives bad
  visual continuity constraints.

### 01 Idea / Memory Residue

Known regression:
- `http://localhost:3002/dream#idea` showed raw JSON/key names in memory cards
  and the Research pane.
- Fix committed: `3f57773e3 fix(persona-dream): extract idea memory JSON text`
- This proves the display layer needed JSON extraction; it does not prove the
  underlying creator/reviewer prompt contract is hardened.

Risk:
- If memory residue is only cleaned for display and not normalized into a typed
  contract, later creator loops may still consume serialized JSON blobs.

## Request

Please optimize the creator-reviewer prompt contract strategy for the whole
spine. Focus on reusable contracts and deterministic proof gates.

Answer these clarifying questions directly:

1. Dependency order:
   Should we implement validators in the order `01 -> 02 -> 06 -> 07`, or start
   with `07` because it already has a closed WebGPT/Tau decision? Choose one.

2. For each spine stage, what is the exact first proof rung?
   Use the same format as the storyboard decision:
   - first patch slice,
   - status names,
   - invalid fixture,
   - positive fixture,
   - deterministic proof command,
   - what remains unverified.

3. What should the reusable prompt contract schemas be named?
   For example:
   - `persona_dream.phase01.memory_residue_contract.v1`
   - `persona_dream.phase02.story_contract_prompt.v1`
   - `persona_dream.phase06.script_prompt_contract.v1`
   - `persona_dream.phase07.panel_prompt_contract.v2`

4. What exact fail-closed statuses should be shared across the spine?
   Examples:
   - `BLOCKED_SERIALIZED_MEMORY_TEXT`
   - `BLOCKED_STORY_CONTRACT`
   - `BLOCKED_SCRIPT_CONTRACT`
   - `BLOCKED_PROMPT_CONTRACT`
   - `BLOCKED_REFERENCE_ATTACHMENT_UNSUPPORTED`

5. What are the key cross-stage invariants?
   Examples:
   - no serialized JSON blobs as display/prompt text,
   - creator cannot write reviewer acceptance,
   - reviewer acceptance requires schema-valid artifacts,
   - downstream stages read typed fields, not prose summaries,
   - visual identity and asset references must be hash-addressed.

6. Which one Tau DAG should we run first after this WebGPT review?
   It should be local-only if possible, provider_live false, mocked false, and
   should prove a closed decision or deterministic validator behavior.

## Desired Output

Return:
- recommended implementation order,
- one first proof rung per stage,
- compact schema names and required fields,
- shared fail-closed status vocabulary,
- cross-stage invariant list,
- first Tau DAG gate to run,
- and explicit non-claims.

Do not provide generic prompt advice. Give a contract-hardening plan that can
be converted into files, validators, fixtures, and Tau DAG receipts.
