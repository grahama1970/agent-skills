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
```

## Fixture Contract

```json
{
  "version": 2,
  "trials": 3,
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

## Readiness Mapping

- `READY`: every case passes every trial.
- `USABLE_WITH_GAPS`: at least one trial passes and at least one trial fails.
- `NOT_READY`: trials ran but no case fully passed.
- `NOT_ESTABLISHED`: no cases were executed.

## Composition

`agentic-evals` composes with `eval-skills`: use `eval-skills` for the existing
repository fixture schema and broad skill regression checks; use
`agentic-evals` when the evaluation needs repeated trials, trajectory-oriented
case typing, and readiness-state output.

Use `audit-skills` after changing `best-practices-skills` eval rules. The audit
does not prove per-skill behavior; it proves the repository's current eval
posture by recording which skills already have fixtures, delegate to eval
skills, document `eval_not_required`, or still emit `EVAL001`.
