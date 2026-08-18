---
name: agentic-evals
description: >
  Agentic evaluation of skills using multi-trial fixtures, deterministic
  command assertions, trajectory checks, safety constraints, and
  evidence-backed readiness scoring. Use when users ask for agentic evals,
  multi-trial skill evaluation, skill trajectory validation, or readiness
  scoring for a skill workflow.
triggers:
  - agentic evals
  - agentic evaluation
  - multi trial skill evaluation
  - skill trajectory validation
  - readiness scoring
  - evaluate agent workflow
runtime_self_improvement: basic
provides:
  - agentic-evaluation
  - multi-trial-evaluation
  - readiness-scoring
  - trajectory-validation-pattern
composes:
  - eval-skills
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - validation
  - resilience
  - precision
disciplines:
  - evaluation-quality
  - agentic-orchestration
---

# agentic-evals

Use this skill when a normal one-shot smoke test is too weak and the task needs
repeatable, evidence-backed evaluation of a skill or agent workflow.

## Current Scope

This initial bundle provides a deterministic fixture runner for command-based
cases. It runs each case multiple times, records stdout/stderr/exit status and
duration, checks explicit expectations, and emits a machine-readable readiness
summary.

This proves only the declared fixture behavior. It does not prove semantic
correctness, real service integration, LLM-judge quality, or release readiness
unless the fixture commands themselves exercise those live paths.

## Usage

```bash
./run.sh run fixtures/agentic_eval.json
./run.sh run fixtures/agentic_eval.json --output /tmp/agentic-evals-report.json
./run.sh audit-skills ../ --output /tmp/agentic-evals-baseline-gap-report.json
./run.sh scaffold-fixture ../some-skill --output ../some-skill/fixtures/agentic_eval.json
./run.sh apply-scaffolds ../ --write --output /tmp/agentic-evals-apply-scaffolds.json
```

## Fixture Contract

```json
{
  "version": 2,
  "skill": "example-skill",
  "trials": 3,
  "proof_scope": "fixture wiring smoke",
  "claims": {
    "proves": "the declared command exits with the expected status",
    "does_not_prove": "semantic correctness, live service behavior, or full skill readiness"
  },
  "cases": [
    {
      "name": "happy-path",
      "type": "positive",
      "command": ["echo", "success"],
      "expected": {
        "exit_code": 0,
        "stdout_contains": ["success"]
      }
    }
  ]
}
```

Each case must declare:

- `name`
- `type`: `positive`, `negative`, or `adversarial`
- `command`: a non-empty argv list
- `expected.exit_code`

Optional expectations:

- `expected.stdout_contains`
- `expected.stderr_contains`

## Anti-Slop Contract (fail-closed)

A skill evaluation fixture is REJECTED at load time (non-zero exit, no run) if it
is self-serving deterministic plumbing rather than real-world proof. To pass, a
skill fixture MUST:

- set `trials` >= 2 (a single trial is not evidence);
- include at least one `negative` or `adversarial` case (an all-positive fixture
  is self-serving);
- include at least one **real-world** case: `"real_world": true` whose command
  exercises a live path (the skill's `run.sh` / a script / live HTTP / a test
  runner) and does NOT feed itself `fixtures/` stub inputs;
- contain no trivial `echo`/constant cases that prove nothing.

Rejection message names every violation. This prevents an eval that passes
trivially while proving nothing about whether the skill actually works.

### Compliance tier (`"eval_tier": "compliance"`)

A fixture that guards a compliance-pipeline stage declares
`"eval_tier": "compliance"` and the runner then MANDATES the strong contract on
top of the baseline (operator directive 2026-08-12, "this is a compliance
pipeline and must be robustly hardened"). Such a fixture is REJECTED unless:

- a **strict majority** of cases are `adversarial`/`negative` (more than half,
  not exactly half — positive controls are the minority);
- at least one case is **non-deterministic**: its command samples fresh inputs
  each run via `--samples`, `--seed`, or a shell `$RANDOM` (a probe *script*
  name with a fixed key does not count);
- every non-deterministic case names `--samples` >= 50, so each stage's coverage
  is hundreds-to-thousands of assertions per run, targeting ~1000 per stage
  across its modes.

The declaration cannot be quietly relaxed: the compliance pipeline's own
fixtures set the tier, so removing it to dodge the gate is itself a regression.
`tests/test_compliance_tier_gate.py` pins each rule against its weakening.

Two honestly-declared exemptions bypass the gate — never valid for a real skill
evaluation:

- `"eval_kind": "runner_selftest"` — a fixture that tests this runner itself or
  is a documentation example.
- `"eval_kind": "scaffold"` — the mechanical first-posture fixture emitted by
  `scaffold-fixture` / `apply-scaffolds`, which the audit still flags as needing
  real cases.

## Readiness Mapping

Readiness is scored over **required** cases only (`"required": false` opts a case
out). A required `BLOCKED` case cannot reach `READY`: an unmet precondition is
absence of evidence, not evidence of success.

- `READY`: every required case passed every trial.
- `USABLE_WITH_GAPS`: at least one trial passed and at least one did not.
- `NOT_READY`: trials ran but no required case fully passed.
- `NOT_ESTABLISHED`: no cases were executed.

## Fail-closed exit

`run` exits **non-zero unless readiness is `READY`**. A runner that exits 0 on
`USABLE_WITH_GAPS` lets an outer CI job go green over failed cases, which is the
whole failure this gate exists to prevent. Pass `--report-only` when you want the
report without the gate.

## Case outcomes

Each case reports one `outcome`, because these mean different things to a gate:

| Outcome | Meaning |
| --- | --- |
| `PASS` | every trial met every expectation |
| `FAIL` | a defect, or a timeout, or a trial that left a child process behind |
| `BLOCKED` | a precondition was unmet; declare markers via `blocked_when_stdout_contains` |
| `NOT_TESTED` | no trials ran |

## Artifact assertions

stdout substring matching cannot express "these two receipts name the same
session" or "the run left nothing behind". Declare `expected.artifacts`:

```json
"expected": {
  "exit_code": 0,
  "artifacts": [
    {"path": "out/session.json", "json_pointer": "/sessionId",
     "equals_artifact": {"path": "out/detach.json", "json_pointer": "/sessionId"}},
    {"path": "out/attach.json", "json_pointer": "/phase", "equals": "attach"},
    {"path": "out/tmp.lock", "absent": true},
    {"path": "out/report.json", "min_bytes": 32, "sha256": "sha256:..."}
  ]
}
```

Paths resolve relative to the fixture directory. Verified artifact hashes are
recorded on the trial.

## Process-group teardown

Each trial runs in its own process group. On timeout the runner kills the
**group**, then re-reads `/proc` and records any survivor in
`orphan_pids_after_teardown`; a non-empty list fails the trial. A timed-out case
that strands a grandchild holding a lock silently corrupts every later case in a
serial run, so teardown is verified rather than assumed.

## Report provenance

The report is `agentic_evals.report.v2` and carries `run_id`, per-case `case_id`,
per-trial `trial_id`, the exact `argv`, `fixture_sha256`, and `repo.sha`/`repo.ref`
when available. It preserves the manifest's own `proof_scope` and `claims`
instead of substituting a generic fixture-only claim, and reports `live: true`
when the manifest declares it or any case is `real_world`. Reports are written
atomically.

Self-tests for every behavior above: `fixtures/runner_selftest.json`.

## Composition

`agentic-evals` composes with `eval-skills`: use `eval-skills` for the existing
repository fixture schema and broad skill regression checks; use
`agentic-evals` when the evaluation needs repeated trials, trajectory-oriented
case typing, and readiness-state output.

Use `audit-skills` after changing `best-practices-skills` eval rules. The audit
does not prove per-skill behavior; it proves the repository's current eval
posture by recording which skills already have fixtures, delegate to eval
skills, document `eval_not_required`, or still emit `EVAL001`.

Use `scaffold-fixture` only as the first mechanical eval posture for a skill. A
generated fixture proves wiring only until a human or maintainer adds
skill-specific positive, negative, and adversarial cases.

Use `apply-scaffolds` to apply that first mechanical posture across all
currently scaffoldable `EVAL001` skills. For skills with `sanity.sh` or
`run.sh`, it creates an entrypoint-backed fixture. For skills without an
entrypoint, it creates a static contract-validation fixture that runs the
`best-practices-skills` validator from the skill's `fixtures/` directory. It
writes only missing `fixtures/agentic_eval.json` files unless `--force` is
passed and emits a JSON receipt. This reduces missing eval posture; it does not
establish semantic coverage.

## Regression Fixture Pattern

When a live incident exposes an agent-troubleshooting failure, add or strengthen
the affected skill's committed `fixtures/agentic_eval.json` instead of leaving
the lesson only in chat. The case should name the failure code, exercise the
real skill entrypoint, script, or test runner, and assert the recovery wording
or receipt fields an agent must see.

Example pattern for browser transport incidents:

- `type: "adversarial"` for stale sockets, stale tab bindings, lock contention,
  missing native host dependencies, or provider payload mismatch.
- `real_world: true` when the command invokes `run.sh`, a real script, live
  HTTP, or the production test runner without feeding itself `fixtures/` stubs.
- `expected.stderr_contains` or `expected.stdout_contains` should include the
  stable failure code such as `stale_socket_no_listener`, not only a generic
  timeout or nonzero exit.

This keeps agentic evals tied to the operational mistake future project agents
need to recognize.
