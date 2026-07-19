# Persona Dream — project-state review request (2026-07-19)

## Objective

Independent GPT review of the persona-dream project state against its README
goals, to be reconciled with an already-received Claude review. You are the
second reviewer. Assess, do not implement.

## current_gate

POST_PHASE16_HARDENING: the founding experiment's machine-decidable boundary is
closed on exactly ONE dream run; the gate under review is whether the project
state supports (a) accepting that closure as real, and (b) the right ordering of
hardening work before a second run.

## Verified state (all receipt-backed at HEAD, read back 2026-07-19)

- Active revision `rev_successor_943b01ecd9a3`, `PASS_ACTIVE_CONSISTENT`,
  acceptance rung v6, 398-artifact immutable index.
- One authorized paid Kling submit; live return `sha256:59b9ff31…` (10.041667s,
  H.264 720p). Step 36 continuity PASS v2 (ArcFace 7/12 frames >= 0.421
  threshold; remaining 5 adjudicated POSE_OCCLUSION via the Tau-routed VLM).
  Steps 37-38 PASS v2 (exact line muxed, force-aligned 4.74-7.86s;
  visible-speaker INAPPLICABLE_BY_COMPOSITION per the lane C design).
- First canonical dream memory written: ArangoDB
  `persona_memory/dream_dream_successor_943b01ecd9a3`
  (`synthetic_origin:true, literal_historical_event:false`), 4 ToM nodes, 14
  edges, exact reread-by-key.
- Phase 16 receipt `overall_status: PASS`: recall from 3 reworded queries
  (ranks 1/3/7) with passing negative control; 14/14 edge traversal; grounded
  dream use marked as a dream; literal occurrence denied.
- All LLM/VLM calls route through Tau (text node at tau `09e64a44`); direct
  scillm from persona-dream scripts is forbidden and eliminated.
- Test suite on fresh state: 29 failed / 313 passed (342). Verified root causes
  include: `schemas/kling_scene_packet.schema.json` removed but still referenced
  by `validate_run_root_pipeline.py`, `validate_pipeline_spine.py`,
  `convert_accepted_storyboard_to_kling.py`, `tests/test_pipeline_spine.py`;
  MANIFEST.json lists 1 schema vs 61 actual schema files.

## Claude review findings to corroborate or dispute (summarized)

1. Research loop genuinely closed for one dream; receipt discipline rigorous;
   fail-closed culture real (four blocked-instead-of-forced receipts).
2. README has become a supersession changelog; Quick Start does not reach the
   proven loop (no run.sh subcommands for the gauntlet/cognitive-loop/phase16
   lane).
3. 29 test failures = bit-rot of the older one-scene dry-run spine lane while
   development moved to the revision/rung lane.
4. Identity is not whole-clip embedding-certifiable (final third cos 0.02-0.15;
   VLM adjudication is the deciding layer, should be corroboration).
5. Lip-sync capability unproven (INAPPLICABLE_BY_COMPOSITION dodges it).
6. Successor observation packet remains DEGRADED (no per-frame VLM entities; no
   transcript on silent pre-mux video); the canonical dream memory cites the
   degraded observation set.
7. Repeatability/generality unproven: one dream, one persona, heavy agent
   repair en route.
8. Claude's proposed order: green CI -> promote Stage B lane to public contract
   -> collapse supersession stacks into receipt-generated status -> tracked
   identity continuity -> voice lane -> second run with zero manual repair ->
   second persona.

## Exact questions

Q1. Do you accept the Phase 16 closure as real for one run, given the evidence
    above — or does any listed gap (DEGRADED packet, VLM-decided identity,
    composition-dodged lip-sync) invalidate the closure claim rather than
    merely bound it?
Q2. Rank the hardening steps (Claude's list plus any you add) by
    risk-reduction-per-effort for reaching a second full dream run with zero
    manual repair. Name the single highest-leverage item.
Q3. Is writing a superseding dream node after enriching the observation packet
    (re-running phases 13-15 on richer observations) the right memory design,
    or should the first canonical write remain the sole node with addenda
    edges? Justify against the "dream must not become false history" rule.
Q4. Any failure mode in the current design that both reviews have missed?

## Acceptance gates for this review

- DIAGNOSIS section addressing Q1-Q4 with explicit agree/dispute per Claude
  finding.
- One ruling: PASS_CURRENT_GATE (state supports closure-as-real + a defensible
  hardening order) or BLOCKED_CURRENT_GATE: <concrete blocker>.

## Forbidden adjacent scope

No code, no diffs, no architecture for phases beyond 16, no provider calls.
