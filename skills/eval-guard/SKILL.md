---
name: eval-guard
description: >
  Deterministic guard against self-serving completion claims and ambiguous
  failure prose. Judges an agent's final message with a checker script, never
  the model itself: a works/complete claim requires a fresh /agentic-evals
  receipt whose fixture has a real real_world case, and a failure report
  requires a strict `Triage: <code>` line from /triage-error's catalog. Ships a
  Pi extension that rejects violating answers on message_end and forces a
  retry with exact diagnostics.
triggers:
  - eval guard
  - self serving unit tests
  - force agentic evals
  - completion claim guard
  - triage classification guard
allowed-tools:
  - Bash
  - Read
provides:
  - completion-claim-enforcement
  - triage-classification-enforcement
composes:
  - agentic-evals
  - triage-error
  - best-practices-pi-extensions
complies:
  - best-practices-skills
  - best-practices-pi-extensions
taxonomy:
  - validation
  - self-improvement
disciplines:
  - engineering-standards
runtime_self_improvement: basic
---

# eval-guard

Unit tests written by the same wrong assumption that wrote the code cannot
prove a feature works, and "something went wrong" hides the failure it should
classify. This guard makes both rules mechanical.

## Checker

```bash
./run.sh --message-file msg.txt                              # prose-only rules
./run.sh --message-file msg.txt --report report.json --skill-dir ../<skill>
```

Exit 0 = clean; exit 1 = violations, as strict JSON
`{ok, violations:[{code, cause, next_command}]}` (triage-style).

| Code | Fires when |
|---|---|
| `completion_claim_without_eval_receipt` | works/complete/verified claim, no report given |
| `proof_laundering_git` | commit/push/SHA presented as the result of an unproven claim |
| `eval_receipt_not_ready` | report readiness != READY |
| `eval_receipt_wrong_skill` | report `fixture_sha256` != the skill's current fixture sha |
| `eval_receipt_stale` | skill files newer than the report, or report older than 24h |
| `eval_receipt_unit_only` | no real_world case that touches a production surface (a case may run unit tests AND run.sh/CLI; pure test-runner cases don't count) |
| `failure_without_triage_code` | failure prose with no `Triage: <code>` line |
| `triage_code_not_in_catalog` | Triage code absent from /triage-error `failure_codes.json` and not a minted `*_unclassified_*` code |

Saying "unverified" exempts a claim: honesty is always a legal exit.

## Pi extension

`pi-extension/index.ts` runs the checker on every `message_end`; a violation
rejects the answer and queues a forced retry via
`pi.sendUserMessage(..., {deliverAs: "followUp"})` carrying the checker's
diagnostics, per the deterministic-desperation-guard rule in
`best-practices-pi-extensions`. Optional env: `EVAL_GUARD_SKILL_DIR`,
`EVAL_GUARD_REPORT`.

The checker is provider-neutral: Claude can run it as a Stop hook and Codex
from its hooks system — one checker, three enforcement points.

## Verification

```bash
../agentic-evals/run.sh run fixtures/agentic_eval.json
```

The fixture drives the real CLI on the full scenario matrix, including a live
`/agentic-evals`-generated report for /triage-error and negative cases for
wrong-skill and unit-only receipts.
