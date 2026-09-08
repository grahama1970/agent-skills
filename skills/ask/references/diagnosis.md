# Ask: Diagnose From Receipts First

The receipt-first dispatch table and the /debugger escalation ladder.
Read on ANY Ask run failure before forming a theory.

## Required Behavior

### Diagnose from receipts first, then `/debugger` (operator 2026-08-04)

The full ladder lives in `$debugger` ("The escalation ladder"). In short:
dispatch on the symptom to the ONE artifact that owns it, escalate to a
breakpoint only when no artifact explains it, and escalate to `$brave-search`
or `$dogpile` only when the observed state is real but its meaning is unknown.
After two failed focused attempts the research rung is mandatory — a third
attempt from the same stale context is not a retry, it is a guess.

When an Ask run fails, read the run directory before forming a theory. Every
large diagnosis on 2026-08-03/04 was already named by a receipt field, and
inference over source produced a patch for a bug that did not exist.

| Symptom | Read this first | It names |
| --- | --- | --- |
| Lane NEEDS_ATTENTION | `node-artifacts/handler-*/node-receipt.json` | `status`, `failure_code` |
| Recovery did not help | `node-artifacts/handler-*/lane-recovery.json` | every rung, or `recovery_budget_exhausted` |
| Lane has no response | `browser-recovery-packet.json` | `failure_code`, `next_command` |
| Panel blocked pre-dispatch | `execution-status.json` → `receipt.alerts` | the exact Tau verdict |
| Seat missing from results | `browser-provider-selection.json` | `removed_handlers` |
| Provisioning blocked | `browser-tab-lifecycle.json` | `failure_code`, `identity_guard`, per-command stderr |
| Contract rejected at compile | `compile-status.json` | `tau_contract_validation` |

**Read a Tau contract violation in full — it is not just a message.** A
`tau.dag_error.v1` payload (pre-dispatch rejection) carries `verdict`,
`failure_code`, `severity`, `evidence.errors[]` naming the exact cause in plain
language, `evidence.primary_alert`, and `recommended_action` with `type`,
`next_agent`, and `reason` — Tau states the next step explicitly. A runtime
block instead puts its detail in `receipt.alerts[]`, each with `code`,
`message`, and an `evidence` object identifying the node and handler. Read every
one of those fields before theorising: `execution_profile_override_broadens_policy:max_concurrency`,
`limits.max_parallel_nodes is not allowed outside extensions`,
`evidence_goal_hash_missing`, and `join_requires_multiple_inputs` each named
their own fix precisely, and each was a real defect.

Only after a receipt fails to explain the behavior, and two focused attempts
have failed, invoke `$debugger`: set a breakpoint in the Ask code path, run the
reproduction, and inspect the paused frame **before** editing. Do not point a
breakpoint harness at a live browser lane — it will sit blocked on Chrome. Use
`surf js --tab-id <id> --no-activate` for live page state instead.

- Build a concrete bundle before review or oracle escalation: objective, target
  files/artifacts, commands already run, uncertainty, exact question, and
  acceptance gates.
- For human requests that ask a named handler/model to answer, solve, review, or
  collaborate, use `./run.sh tau-dag ...` as the modern front door. `$ask`
  compiles the request into a strict `tau.dag_contract.v1` bundle, emits
  `dag.json` before execution, uses `$interview` when required DAG fields are
  missing, and delegates execution and live status/viewer polling to `$tau`.
- Treat modern roundtable and creator-reviewer loops as prompt-to-Tau-DAG. The
  user should only need to name handlers and shape: single call, concurrent
  roundtable, creator-reviewer pipeline, compete/bakeoff, or explicit
  multi-step DAG. It must not matter to the user whether a handler is
  browser-backed or API-backed except for the handler/model name they request.
- Roundtable, creator-reviewer, and compete/bakeoff handler DAGs require an
  explicit immutable goal or acceptance bar. Pass it with `--immutable-goal` or
  label it in the request as `Immutable goal:`, `Acceptance bar:`, or
  `Stop condition:`. If it is missing, `$ask` must fail preflight with
  `NEEDS_INTERVIEW` before any browser or API handler is contacted. The same
  immutable goal is shared with every participant and included in the Tau goal
  hash.
- For substantial roundtables, apply `$best-practices-roundtable` as the
  leadership contract: equal shared context, concurrent seats, attributed
  dissent, research between rounds, and executable slices before local proof.
- For substantial compete/bakeoff workflows, apply
  `$best-practices-competition`: isolated candidates, identical task packets,
  local feature verification, evidence-backed winner selection, and
  winner-only continuation until the immutable goal is met. Treat iterative
  competitions as dynamically expanding Tau DAGs, or as linked next-round DAGs
  under the same immutable goal hash when the installed runtime cannot append
  nodes in place. Do not share participant information between candidate lanes
  or rounds; help each lane only with its own review, local evidence, and
  permitted research tools.
- Pass the bundle to the documented ask mode. Do not compress a review target
  into an informal prompt when the mode has a target option.
- Report artifact paths as evidence. Browser reviewers or model
  reviewers are not deterministic proof by themselves.
- Direct WebGPT/ChatGPT oracle routing is not an `$ask ask` backend: `$ask
  webgpt`, `$ask chatgpt`, `--oracle-backend webgpt`, `--webgpt-*`, and
  `webgpt-project` must fail closed. This does not ban Tau roundtable
  `webgpt`: `webgpt` is a supported Tau browser handler routed through `$surf`.
- Close only from local deterministic proof appropriate to the task: tests,
  schema checks, endpoint responses, screenshots, database/query evidence, or
  generated artifact validation.
- Fail closed when tab binding, target file, reviewer configuration, browser
  state, or runtime artifact creation is missing.
- Use readiness language when proof is incomplete: `NOT_READY`,
  `NOT_ESTABLISHED`, `NEEDS_ATTENTION`, or `BLOCKED`, with the missing proof
  named explicitly.
- Provider/model execution in generated Tau DAGs is Tau-owned: `$ask` emits
  local adapter nodes and Tau dispatches their command specs; those adapters
  call the `$scillm` container service (`http://127.0.0.1:4001` by default).
  Real provider calls require explicit `--allow-provider-calls`. Use
  `--local-fixture` only for Tau scheduler sanity proof; report that it does
  not prove provider/model behavior.

