# T'au Project Knowledge

This skill is a light wrapper around `${HOME}/workspace/experiments/tau`.
It does not implement Tau behavior itself.

## Current Evidence Boundaries

- 2026-07-06 UX Lab now has a read-only Tau DAG React Flow inspection route at
  `http://localhost:3002/#tau/dag`. Commit `711b9c051` in `pi-mono` added a
  Tau-specific adapter from `tau.dag_contract.v1` plus `tau.dag_receipt.v1`
  into the existing transport DAG evidence model, static fixture artifacts under
  `packages/ux-lab/public/tau-dag-runs/`, and a side panel for receipt status,
  goal hash, mocked/live/provider-live boundaries, alerts, proof scope, and
  artifact paths. Focused proof observed `npm run test --
  src/components/tau/tauDagEvidenceAdapter.test.ts
  src/components/scillm/transport/TransportReactFlowDagWorkspace.test.ts` with
  `15 passed`, and CDP verification wrote
  `/home/graham/workspace/experiments/pi-mono/.codex/ui-verification/latest.json`
  plus screenshot
  `/tmp/codex-ui-verification/pi-mono/tau-dag-react-flow/20260706T150412Z.png`.
  This proves artifact-backed DAG renderability in the browser; it does not
  prove live Tau DAG execution from the browser, Herdr provider execution,
  GitHub mutation, provider/model semantic quality, or human acceptance.
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
- DAG UI claims need browser/CDP screenshot inspection against
  `http://localhost:3002/#tau/dag` and must preserve the source DAG contract and
  receipt paths.
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
5. DAG viewer: UX Lab React Flow inspection route for read-only DAG
   contract/receipt visualization.

The special long-running mode is not a forever-running subagent. Cron or GitHub
Actions may run repeatedly as infrastructure, but each subagent invocation must
be bounded and must emit a receipt with goal, context, result, rationale, next
agent, required evidence, and stop condition.
