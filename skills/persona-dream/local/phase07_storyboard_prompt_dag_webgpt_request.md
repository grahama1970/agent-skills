# WebGPT Architecture Review Request: Persona Dream Phase 07 Storyboard Prompt DAG

Please review and optimize the DAG/prompt architecture for Persona Dream Phase 07 sequential storyboard generation.

Explicit ChatGPT binding requested by human:
- name: dreams
- URL: https://chatgpt.com/c/6a4c25f5-1460-83ea-83cc-e63ce7a497d9
- tab id: 837358015
- Desktop: 2

## Current Status

The four-panel storyboard is accepted by Tau:
- Final Tau receipt: `skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau/tau-run-sequential-storyboard-final-20260707T212418Z/dag-receipt.json`
- Receipt fields: `ok=true`, `status=PASS`, `verdict=PASS`, `live=true`, `mocked=false`
- Storyboard packet: `skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau/storyboard_packet.json`
- UI screenshot was inspected locally and showed `PASS PANEL REVIEWED` with `4 PANELS`; the screenshot itself is not attached because this request is about DAG/prompt architecture, not visual acceptance.

The accepted artifact proves the storyboard was produced and reviewed. It does not prove that the creator DAG is efficient or that the prompts are competent.

## Problem To Solve

The prompt/DAG path is defective:
- `sb004` took roughly 13 minutes end-to-end because it required a repair loop.
- The first `sb004` review rejected identity continuity for Embry.
- The creator prompt did not bind identity/reference/continuity constraints tightly enough before live image generation.
- Tau correctly caught the defect; Tau should not be the main mechanism for making vague prompts usable.

The desired common-case bound is no more than 5 minutes per panel for generation plus review. Repair loops may exist, but the prompt contract should make them rare and diagnostic.

## Architecture Artifact

Created through `$create-architecture`:
- Source YAML: `skills/persona-dream/local/phase07_storyboard_prompt_dag_architecture.yaml`
- Expected project/view: `Persona Dream Phase 07 Sequential Storyboard Prompt DAG Repair` at `http://localhost:3002/#architecture`

## Files Worth Inspecting

- Creator/reviewer node implementation: `skills/persona-dream/scripts/phase07_storyboard_tau_node.py`
- Storyboard packet: `skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau/storyboard_packet.json`
- Panel contract: `skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau/storyboard_panel_contract.generated.json`
- Final Tau receipt: `skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau/tau-run-sequential-storyboard-final-20260707T212418Z/dag-receipt.json`
- Example problematic prompts:
  - `skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau/receipts/storyboard_frame_generation/sb_004_start_frame.prompt.md`
  - `skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau/receipts/storyboard_frame_generation/sb_004_end_frame.prompt.md`

## Review Questions

1. How should the DAG be restructured so prompt compilation is deterministic and reviewable before any live image call?
2. What fields must exist in each per-panel prompt to make identity, wardrobe, environment, camera, continuity, and negative constraints non-vague?
3. What preflight validator should run before image generation to block underspecified prompts?
4. How should Tau reviewer feedback be converted into targeted prompt patches without causing slow broad regeneration?
5. What receipt schema should prove that each panel stayed under the common-case 5-minute budget or explain exactly why it did not?
6. What is the minimal patch plan for `phase07_storyboard_tau_node.py` and the DAG contracts?

Please return:
- an optimized DAG,
- concrete prompt contract fields,
- a validator checklist,
- a repair-loop policy,
- a minimal implementation plan,
- and risks/unknowns that still need live proof.
