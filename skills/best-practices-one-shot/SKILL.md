---
name: best-practices-one-shot
description: >
  Best practices for Ask one-shot runs: the same question to N seats
  concurrently, answers returned per seat with no consensus, no judge, and no
  quorum. Use when a user asks several models one question and wants to read
  each answer, when partial answers are still useful, or when deciding whether
  a request is a one-shot, a roundtable, or a competition.
triggers:
  - one-shot best practices
  - ask one-shot
  - per-seat answers
  - ask several models one question
  - no consensus panel
  - independent answers
provides:
  - one-shot-contract
  - deliverable-driven-mode-routing
  - honesty-vs-readiness-split
composes:
  - ask
  - best-practices-tau-dag
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-tau-dag
taxonomy:
  - orchestration
  - querying
disciplines:
  - engineering-standards
  - agentic-orchestration
---

# Best Practices: One-Shot

A one-shot asks N seats the same question concurrently and returns N
independent answers. The human reads the answers; nothing synthesizes them.
It is the correct mode when the deliverable is perspectives, not a decision.

## Core Rule

Never manufacture agreement from one-shot answers.

The moment you summarize the answers into "the models agree that..." you have
run a roundtable without its equal-packet, quorum, and attributed-dissent
guarantees. The moment you pick "the best answer" you have run a competition
without isolation or an independent judge. If the user wants either, recompile
in the right mode; do not upgrade a one-shot in prose.

## Contract

`skills/ask/run.sh one-shot "<question>" --handler <a> --handler <b> ...`

- **Independence is structural.** Each seat runs as its own single-call Tau
  DAG. There is no shared node, so one seat's failure cannot reach another
  lane even in principle — stronger isolation than a roundtable's join-gate.
- **Nonce-bound answers.** The prompt embeds a fresh token the answer must
  echo; a response without this run's nonce is `STALE_OR_UNBOUND`, never an
  answer. A stale artifact can never be graded as this run's result.
- **Honesty and readiness are separate verdicts.** Per seat: `ANSWERED`,
  `NAMED_BLOCKER` (non-empty failure_code), or `DISHONEST` (neither). Run
  level: exit 0 at or above `--min-answered`, exit 3 when every lane was
  honest but answers fell below the floor, exit 1 only for dishonest lanes.
  1/3 answers is a usable result, not a failure.
- **Receipts per seat.** Every lane leaves its own run dir with
  `response.md`, `node-receipt.json`, `dag-chart.initial.txt`, and
  `dag-chart.final.txt`; the run writes `one-shot-verdict.json`. Report from
  these artifacts, never from memory of the stdout.

## Choosing the mode (deliverable-driven)

| The user wants | Mode |
| --- | --- |
| To read N perspectives themselves | one-shot |
| One deliberated position with dissent attributed | roundtable (`$best-practices-roundtable`) |
| One winner chosen on evidence from isolated attempts | compete (`$best-practices-competition`) |
| One answer from one model | `$ask` single handler |

Cues in the request: "ask A and B and C <question>" with no synthesis verb is
a one-shot. "Discuss / debate / recommend" is a roundtable. "Each implement /
pick a winner / judge" is a competition.

## Charts are part of the run

Before executing, show the human the compiled DAG chart
(`dag-chart.initial.txt`, printed at compile). After the run, read and report
the final verdict chart (`dag-chart.final.txt`) — per-node PASS / FAIL /
NAMED_BLOCKER / NO_RECEIPT — so what succeeded and failed is visible without
trusting prose. The final chart is also the project agent's self-correction
instrument: every non-PASS node is a work item to read, fix, rerun, or name
before reporting. Both artifacts are eval-enforced in `$ask`.

## Fail-Closed Rules

| Condition | Behavior |
| --- | --- |
| Answer missing this run's nonce | `STALE_OR_UNBOUND`, lane fails |
| No answer and no failure_code | `DISHONEST`, run exits 1 |
| Zero answers, all blockers named | honest but `NOT_READY`, exit 3 |
| Caller summarizes answers into consensus | wrong mode; recompile as roundtable |
| Caller ranks answers and declares a winner | wrong mode; recompile as compete |

## Common Failure Modes

| Failure mode | Required correction |
| --- | --- |
| Consensus prose over independent answers | Report per seat, or rerun as roundtable |
| "Best answer" selection without a judge | Rerun as compete with `--judge-handler` |
| Treating a named blocker as a failure | It is honest; count it against readiness only |
| Treating an all-blocked run as a pass | Exit 3 NOT_READY is the contract |
| Reporting from stdout memory | Read `one-shot-verdict.json` and lane receipts |

## Agentic Evals

The live contract is proven by `skills/ask/fixtures/agentic_eval_live.json`
case `live-one-shot-asks-mixed-seats-and-returns-per-seat-answers` (runner
level, two trials), with the verdict machinery red-teamed by the ladder and
judge-audit adversarial cases. Do not add deterministic-only proof for live
behavior; extend the live fixture instead.
