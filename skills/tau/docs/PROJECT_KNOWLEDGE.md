# T'au Project Knowledge

This skill is a light wrapper around `${HOME}/workspace/experiments/tau`.
It does not implement Tau behavior itself.

## Current Evidence Boundaries

- 2026-07-05 wrapper catch-up: `skills/tau/scripts/tau_skill.py` now expands
  Tau paths via `Path.home()` / `TAU_ROOT`, exposes `doctor`, exposes
  `proof-status`, and keeps `e2e` only as an alias reporting
  `alias_for: proof-status`.
- 2026-07-05 wrapper proof: `skills/tau/run.sh doctor` emitted
  `agent_skills.tau.doctor.v1` with `ok:true` and nested Tau runtime
  `tau.doctor.v1` with `status:"PASS"`. `skills/tau/run.sh proof-status`
  emitted `agent_skills.tau.proof_status_receipt.v1` with `ok:true`,
  `sanity_ok:true`, and `status_ok:true`. `skills/tau/run.sh e2e` emitted
  `agent_skills.tau.e2e_receipt.v1` with `alias_for:"proof-status"`.
- Full Tau pytest was observed with `804 passed in 60.36s`.
- Live project-watchdog issue repair was observed on `grahama1970/tau#3`.
- Tau commit pushed for that repair: `19cd3697d9d834fa049948a7a4fdfcab1076f0ec`.
- Watchdog receipt for the live issue lane:
  `${HOME}/.local/state/project-watchdog/receipts/project-watchdog-20260628T120401Z/receipt.json`.
- Project-watchdog cron is installed and writes receipts under:
  `${HOME}/.local/state/project-watchdog/receipts/`.

## Pending Proof Boundaries

- The skill alone does not prove fresh browser chat rendering.
- Chat UI claims need `test-interactions` manifests and browser/CDP screenshot
  inspection against the host route.
- The skill alone does not prove production Sparta Chat readiness.
- Unit tests prove code paths only; live GitHub mutation and browser proof need
  separate receipts.

## Operating Model

Tau has four major surfaces:

1. Loop: command-loop and provider execution, including Chutes and fake-provider
   lanes.
2. Harness: goal-locked handoff contracts, subagent routing, immutable human
   goal handling, and GitHub ticket orchestration.
3. TUI: terminal-facing state and proof inspection.
4. Chat: Memory-first React chat renderer intended to converge with Watch and
   Sparta Chat UX patterns.

The special long-running mode is not a forever-running subagent. Cron or GitHub
Actions may run repeatedly as infrastructure, but each subagent invocation must
be bounded and must emit a receipt with goal, context, result, rationale, next
agent, required evidence, and stop condition.
