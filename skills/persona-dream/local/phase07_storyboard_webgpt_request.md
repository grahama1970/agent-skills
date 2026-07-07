# WebGPT Architecture Review Request: Persona Dream Phase 07 Storyboard DAG

You are reviewing a live, receipt-backed Tau DAG workflow for sequential storyboard generation.

## Goal

Optimize the Persona Dream Phase 07 storyboard DAG before the remaining panels continue.

The required end state is:

1. `sb_001` reviewer-accepted end frame feeds `sb_002`.
2. `sb_002` reviewer-accepted end frame feeds `sb_003`.
3. `sb_003` reviewer-accepted end frame feeds `sb_004`.
4. Final full-storyboard approval is a no-target Tau reviewer pass over all four panels.

Tau reviewer acceptance is the approval boundary. Creator nodes may produce candidate frames only; reviewer nodes own `accepted_frame`.

## Current Evidence Summary

`sb_001` was accepted in a prior targeted Tau run.

`sb_002` initially failed because the prompt demanded both Embry and Kai but the adapter only attached Embry as a panel-level identity reference. After patching the adapter so every panel requires both Embry and Kai, `sb_002` passed Tau reviewer identity review.

`sb_003` has now passed Tau reviewer identity review using `sb_002.end_frame` as its temporal continuity reference.

`sb_004` has not been started in this architecture-review handoff. Final full-storyboard approval has not been run.

## Problems To Solve

1. Target scoping was unsafe.
   - The adapter overwrote explicit `generation_scope` to `sb_001`.
   - Validation/generation/review walked non-target panels during target-scoped runs.
   - This risked blocking a panel on future panels that could not yet be accepted.

2. Retry edges were missing from the DAG.
   - Reviewer rejection correctly routed `panel-reviewer -> panel-creator`.
   - The first DAG allowed only `panel-creator -> panel-reviewer -> human`.
   - Tau blocked with `unexpected_edge` and `max_steps_exhausted`.

3. Prompt and adapter truth were mismatched.
   - Prompt said Embry and Kai were mandatory identity references.
   - Panel metadata sometimes only required one identity.
   - Reviewer could not verify the missing identity reference and rejected the frame.

4. Prompt payloads are overloaded.
   - Each image prompt asks for identity, temporal continuity, surf action, reef, heat, wax, lighting, emotion, negative constraints, and cinematic style.
   - Identity is the hard acceptance criterion, but the prompt still gives too much competing work to the image generator.

5. Latency is high.
   - The live image route uses a nested Codex/image generation tool call.
   - One panel can take several minutes for two frames plus review.
   - Parallelizing panels is not allowed because it would break continuity.

## Current Patch Under Review

The patch currently:

- preserves explicit `generation_scope`;
- skips non-target panels during targeted generation/review;
- adds both Embry and Kai as required identities for every generated/reviewed panel;
- keeps final no-target review as the full approval gate.

## Requested Architecture Output

Please propose an optimized DAG/prompt architecture that preserves these invariants:

- Sequential only: no panel can generate until previous panel end frame is reviewer-accepted.
- Identity-first: Embry/Kai reference verification outranks action, reef, and visual beauty.
- Reviewer-owned acceptance only: creator cannot write accepted frames.
- Live evidence only: mocked tests are wiring-only and cannot approve panels.
- Repair loops are bounded and receipt-backed.
- Final approval is a no-target all-panel Tau review.

Answer with:

1. The recommended DAG shape.
2. The recommended retry/repair loop.
3. Whether generation should be one frame at a time or two frames per panel.
4. How prompt blocks should be ordered and simplified.
5. What receipts and invariants should exist before unlocking the next panel.
6. What current patch risks remain.

The attached zip contains the architecture review bundle, architecture YAML, current adapter diff, key Tau DAG contracts, and key receipts.
