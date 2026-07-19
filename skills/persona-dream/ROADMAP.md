# Persona Dream roadmap (draft r1, 2026-07-19)

Seeded from three external reviews (Claude, GPT project-state, Sol Pro) minus
everything already closed (CI green; P0 state machine + transactional
persistence, 5-round adversarially certified + live fault-proven; routing
enforcement + debt paid; observation packet v2 ACCEPTED; weeks-1-2 integrity
fixes; GMO schema/visibility/activation ownership; phases 13-16 live-proven on
one accepted return). Current truth: CURRENT_STATE.md.

## P0 — before/around the pilot

1. Pilot setup: frozen R1/R2 root-set selection addendum (scripted, 3 rules)
   + producer-blinding receipt mechanism (prompt-content hash vs probe
   denylist). Then run the frozen C-vs-F pilot (protocol v2), operator blind
   read (M5), publish the result either way.
2. Human subjective acceptance of dream-004's video (operator watches it;
   human-authored receipt; never machine-fabricated).

## P1 — quality debts with named owners

3. Routing semantics (issues/428): preserve message-role hierarchy through
   Tau nodes; montage verdict-equivalence calibration on the
   reviewer_calibration_v4 frame set; enforce (not advise) ArcFace authority
   at identity call sites.
4. Versioned 13-15 re-run on the enriched v2 packet as revision bundles
   (PROV wasRevisionOf; same dream node — GPT review's memory design).
5. GMO follow-ups: merge the two GMO branches into its mainline (human owns
   the diverged main); commit-lifecycle endpoints (staging/commit-open)
   server-side; persist Watch observations as multimodal Qdrant points
   (cross-modal recall: "what did the dream look like").
6. Identity certifiability: tracked temporal identity (face tracking across
   the clip, pose-aware thresholds, per-beat expectations) so whole-clip
   identity is embedding-certified, VLM demoted to corroboration.

## P2 — capability completion

7. Voice lane: native Chatterbox render of an Embry post-dream performance
   (affective-performance contract -> voice_expression_plan.v2), dual-route
   evaluation (PED-style text/audio), one deliberately visible-speaker shot
   through the lip-sync canary so item 10 stops being out of scope.
8. Repeatability: second full dream run, frozen policy, zero receipted
   interventions; then a second persona/fixture. Two-wave concurrent frame
   generation lands here (recorded decision).
9. dream CLI: run.sh dream start/observe/interpret/promote/evaluate/resume,
   manifest-driven, idempotent; README Quick Start rewritten around it.

## Explicitly parked

- Full A-G publishable ablation (only after the cheap pilot signals).
- Autonomous dream scheduling by emotional salience; React Flow canvas.
- State-promotion ladder + causal-family enforcement beyond current fields
  (needs multiple dreams to be meaningful).
