# WebGPT Follow-Up: Phase 07 Storyboard Prompt DAG Clarifications

Continue the Persona Dream Phase 07 storyboard prompt DAG review in this same conversation.

You already returned the key invariant:

> No live image call may start until the per-frame prompt contract proves required identities, reference attachments, camera feasibility, continuity references, negative constraints, and generation scope.

I agree with that direction. I need the next answer to resolve implementation ambiguities so the project agent can make a narrow patch instead of inventing architecture locally.

## Context

Current accepted storyboard proof exists, but it is not efficiency proof:
- Tau accepted the final 4-panel storyboard.
- `sb004` took roughly 13 minutes because the creator prompt path triggered a repair loop.
- The target common case is <=5 minutes per panel.
- The likely defect is prompt/DAG structure, not Tau review strictness.

Current core file:
- `skills/persona-dream/scripts/phase07_storyboard_tau_node.py`

## Clarifying Questions

1. What is the smallest first patch that proves the new architecture without rewriting the entire DAG runner?

Please choose exactly one first implementation slice:
- A. prompt contract JSON + deterministic validator only, no live generation changes yet
- B. provider reference attachment proof first
- C. timing budget receipts first
- D. split creator node into multiple Tau nodes first

Explain why your chosen slice is the correct first proof rung.

2. If the current image provider cannot attach reference images as actual image inputs, should generation fail closed immediately, or should text-only generation remain allowed with a degraded receipt?

Give the exact receipt fields and terminal status you recommend.

3. What should the deterministic prompt validator do with `Kai required` plus language such as `spatially implied`, `secondary`, `understated`, or `not the focus`?

Define the allowed and forbidden vocabulary precisely enough for a simple validator.

4. Should start and end frames for a panel be generated in parallel after prompt validation, or should start frame generation feed end frame generation?

Answer for Phase 07 specifically, where storyboard continuity exists but each panel has start/end frame slots.

5. What are the minimum required fields for `prompt_contracts/{panel_id}.{frame_id}.attempt_{n}.json`?

Return a compact schema skeleton, not a large example.

6. What is the exact acceptance gate for the first patch?

I need deterministic proof commands and artifact checks. Include what the proof does and does not prove.

## Desired Output

Return:
- chosen first patch slice,
- exact fail-closed statuses,
- compact prompt contract schema,
- validator rule list,
- timing receipt minimum,
- deterministic proof checklist,
- and what should remain explicitly unverified until a fresh live run.
