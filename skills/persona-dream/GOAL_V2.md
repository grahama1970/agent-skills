# Persona Dream Immutable Goal v2 (controlling)

Created: 2026-07-19 via /goal-helper from the webgpt-converged ROADMAP r2
(PLAN_STABLE). Supersedes GOAL.md's v1 goal, whose media-spine objective (a
working Kling video) is fulfilled at agent level; v1 remains immutable
history. This goal is immutable: no agent may weaken, reinterpret, or replace
it without an explicit human-authored supersession note here.

## Goal

/goal Close the founding-experiment P0 boundary: one non-superseded v2-derived
evidence lineage, a proven Embry voice expression, and the executed frozen
C-vs-F pilot with a published result.

## Primary proof

- `python3 scripts/check_goal_v2_boundary.py --json` exits 0 with status
  `PASS_GOAL_V2_P0_BOUNDARY`, validating on disk (by hash-bound receipts):
  P0.2 lineage receipt, P0.3 routing-semantics calibration receipt, P0.4 GMO
  deployment pin, P0.5 v2-derived phase-16 receipt, P0.6 voice expression +
  dual-route evaluation receipts, P0.7 pilot result receipt
  (positive/null/invalid all count — published under the frozen rules), and
  P0.1 human acceptance receipt (human-authored; the checker verifies
  presence and hash-binding, never authors it).

## Completion criteria

- P0.1 human acceptance receipt exists, hash-bound to video sha256:59b9ff31…
  (HUMAN-authored; machine-fabrication is goal failure).
- P0.2 phases 13-16 rerun from accepted observation packet v2 as revision
  bundles: single dream-event node untouched, superseded derived evidence
  marked via supersedes edges, new bundle written through the certified
  transactional path, CURRENT_STATE regenerated from the new lineage,
  drift-check green.
- P0.3 issues/428 closed: role hierarchy preserved through Tau nodes, montage
  verdict-equivalence calibrated on the reviewer_calibration_v4 set, ArcFace
  authority enforced at identity call sites.
- P0.4 the exact deployed GMO commit is pinned in every new run manifest (or
  the human has merged GMO mainline).
- P0.5 phase-16 evaluation passes against the v2-derived lineage.
- P0.6 an Embry post-dream performance renders through Chatterbox with
  dual-route (text/audio) evaluation receipts; one visible-speaker lip-sync
  canary receipt. No paid provider video call.
- P0.7 the C-vs-F pilot executes under frozen protocol v2 with the R1/R2
  addendum + producer-blinding receipts; result published under the frozen
  decision rule; the operator's M5 blind read receipt is human-authored.

## Allowed scope

- skills/persona-dream (scripts, schemas, contracts, tests, receipts, docs).
- Tau nodes for all LLM/VLM calls; skills/watch call-site fixes for P0.3.
- GMO repo for the deployment pin surface only.
- Chatterbox transport for P0.6 rendering + evaluation.

## Forbidden drift

- Anything in ROADMAP P1/P2 (temporal identity tracking, clean-room envelope,
  dream CLI, second run, second persona, concurrency, multimodal Qdrant,
  full ablation) unless a P0 proof literally requires it.
- Paid provider video calls of any kind.
- Weakening any certified gate (transaction layer, routing boundary, frozen
  protocol) to make a proof pass.
- Re-litigating closed review gates.

## Retry/stop rule

- Two focused attempts per blocker, then a blocker report: exact failed
  command, exact output, files changed, artifact paths, current hypothesis,
  one recommended next action. Human-owned items (P0.1, M5 read, GMO merge)
  block only their own criterion, never the others.

## Final report contract

- Report the primary-proof command output plus per-criterion receipts.
- Never claim completion without the primary proof exiting 0.
