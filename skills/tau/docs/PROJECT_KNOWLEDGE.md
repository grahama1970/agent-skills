# T'au Project Knowledge

This skill is a light wrapper around `${HOME}/workspace/experiments/tau`.
It does not implement Tau behavior itself.

## Current Evidence Boundaries

- 2026-07-17 canonical five-workflow alignment: `workflows-list` exposes
  `repository-readiness`, `tau-operator-reference`, `repository-evidence-map`,
  `approved-release-bundle`, and `durable-repository-qualification`. The wrapper
  forwards the fifth workflow's publish path and exposes bounded
  `workflow-repair`, `workflow-approve`, and `workflow-resume` commands. Tau's
  installed-wheel receipt is
  `/tmp/tau-durable-qualification-wheel-proof.json`; its live React Flow receipt
  is `/tmp/tau-durable-qualification-browser-proof.json`, with desktop and
  mobile screenshots beside it under `/tmp`. These Tau receipts report
  `mocked:false`, `live:true`, `provider_live:false`; wrapper tests prove command
  routing only.

- 2026-07-13 live WebGPT clarification acceptance: Tau ran one native
  `architecture_review/webgpt` skill node against Browser Oracle project `tau`
  and exact tab `837358072`. Round 1 returned `CLARIFY`; the human selected
  `route_human`; round 2 returned `PASS` at the immutable `2/2` limit; and a
  later DAG invocation reused the accepted receipt without creating round 3.
  The answer SHA-256 was
  `b5c3a0231ce59f22f0598636ad1700a5b21877f48d482f4646ceaecd709571be`.
  Surf recorded `proof_status:"response_proven"`, matching requested and
  controlled tab ids, `raw_contains_sentinel:true`, `focus_changed:false`, and
  `transport_degraded:false`. Artifacts are under
  `/tmp/tau-skill-clarification-live-20260713T1255Z/`. This was
  `mocked:false`, `live:true`, and `provider_live:false`.

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
- 2026-07-17 Slice 01 wrapper contract: the operator entrypoint exposes
  `workflows-list`, `workflow-describe`, `workflow-run`, `dag-view`, and
  `dag-view-capabilities` as bounded invocations of the Tau checkout selected by
  `TAU_ROOT`. `doctor` queries `tau workflows list --json` and
  `tau dag-view-capabilities --json`; it reports canonical-workflow and
  Tau-owned-viewer capability booleans only when those commands succeed.
  Repository-readiness result artifacts are expected at
  `<run-dir>/results/repository-readiness.json` and
  `<run-dir>/results/repository-readiness.md`. Live positive and negative
  screenshots and proof receipts belong to the Tau repository's Slice 01 proof
  run; this wrapper change does not fabricate or replace them. The named Tau
  backend proofs now report PASS; this repository's focused tests still prove
  wrapper routing only.

### Canonical Workflow Slice 01 Operator Contract

Exact wrapper commands:

```bash
skills/tau/run.sh workflows-list
skills/tau/run.sh workflow-describe repository-readiness
skills/tau/run.sh workflow-run repository-readiness \
  --repo /path/to/repository \
  --goal "Determine whether this checkout is ready for focused work." \
  --require-clean \
  --run-dir /tmp/tau-repository-readiness \
  --open-viewer
skills/tau/run.sh dag-view /tmp/tau-repository-readiness
skills/tau/run.sh dag-view-capabilities
```

Expected result artifacts from the Tau backend:

```text
<run-dir>/results/repository-readiness.json
<run-dir>/results/repository-readiness.md
```

Required live proof artifacts from the Tau backend Slice 01 proof run:

```text
/tmp/tau-repository-readiness-positive-proof.json
/tmp/tau-repository-readiness-positive.png
/tmp/tau-repository-readiness-negative-proof.json
/tmp/tau-repository-readiness-negative.png
/tmp/tau-repository-readiness-wheel-proof.json
```

Agent-skills wrapper proof: `uv run --project skills/tau pytest -q
skills/tau/tests` passed `5` tests on 2026-07-17. This is deterministic wrapper
evidence with `mocked: true`, `live: false`, and `provider_live: false`; it does
not independently prove the Tau backend. The named Tau receipts provide the
separate live evidence: positive and negative browser receipts report PASS with
GET-only traffic, and the wheel receipt reports `mocked:false`, `live:true`,
`provider_live:false` after importing Tau from the temporary wheel installation
and executing the three-node workflow.
- Full Tau pytest was observed with `804 passed in 60.36s`.
- Live project-watchdog issue repair was observed on `grahama1970/tau#3`.
- Tau commit pushed for that repair: `19cd3697d9d834fa049948a7a4fdfcab1076f0ec`.
- Watchdog receipt for the live issue lane:
  `${HOME}/.local/state/project-watchdog/receipts/project-watchdog-20260628T120401Z/receipt.json`.
- Project-watchdog cron is installed and writes receipts under:
  `${HOME}/.local/state/project-watchdog/receipts/`.

## Pending Proof Boundaries

- Secure execution still needs a host-compatible positive isolated command,
  grant-scoped mounts, explicit secret/network grants, retry grant renewal, and
  Docker/Docker-Sandbox integration.
- Course-correction receipts still need general execution and follow-through
  verification, not only decision artifacts.
- A real OMP binary, broader controlled-data worker demo, asymmetric signing,
  append-only audit ledger, and authenticated/RBAC API remain pending.
- Provider/model semantic quality and arbitrary future skill-route correctness
  remain explicit non-claims.

- The skill alone does not prove fresh browser chat rendering.
- Chat UI claims need `test-interactions` manifests and browser/CDP screenshot
  inspection against the host route.
- DAG UI claims need browser/CDP screenshot inspection against the packaged Tau
  viewer opened by `skills/tau/run.sh dag-view <run-dir>` and must preserve the
  source DAG, journal, run receipt, screenshot, and browser-proof paths.
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
5. DAG viewer: packaged Tau React Flow application for read-only,
   journal-authoritative workflow inspection.

The special long-running mode is not a forever-running subagent. Cron or GitHub
Actions may run repeatedly as infrastructure, but each subagent invocation must
be bounded and must emit a receipt with goal, context, result, rationale, next
agent, required evidence, and stop condition.
