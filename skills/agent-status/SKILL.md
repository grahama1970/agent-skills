---
name: agent-status
description: >
  Artifact-driven status surfaces for long-running project-agent work. Maintains
  status.json, events.jsonl, proof manifests, and a stale-aware STATUS.html so
  humans can tell where the agent is, what passed, what is still unproven, and
  what decision or action is next — without dashboard theater.
triggers:
  - agent status
  - status page
  - progress page
  - where are we
  - show status
  - update status
  - make status visible
  - project agent status
  - status artifact
  - status html
  - status ledger
  - proof manifest
  - campaign status
provides:
  - agent-status
  - progress-tracking
composes: []
taxonomy:
  - observability
  - orchestration
disciplines:
  - observability-operations
  - agentic-orchestration
---


# agent-status

Use this skill whenever a project agent is doing multi-step work and the human
needs to know what is actually happening.

This skill is intentionally **not a dashboard generator**. It produces a truth
surface backed by machine-readable artifacts:

```text
.plan-iterate/<campaign-id>/status/
  status.json
  events.jsonl
  proof_manifest.json
  STATUS.html
```

The HTML only renders the current status artifact. It must not invent progress,
percentages, or completion claims.

## Core principle

```text
status artifact first → HTML renders artifact → human can inspect proof
```

Never do this:

```text
pretty page first → vague green language → human infers progress
```

## Required first-viewport answers

A generated status page must answer:

1. What is the agent trying to finish?
2. Where exactly are we?
3. What just passed?
4. What is still not proven?
5. What is the next action?
6. Is the agent running, blocked, idle, or waiting for the human?
7. What proof backs the current claim?
8. What should the agent not do next?

## State model

Allowed states:

- `not_started`
- `running`
- `needs_attention`
- `blocked`
- `failed`
- `passed_scoped_gate`
- `done`
- `idle`

Important distinction:

```text
passed_scoped_gate != done
```

Only use `done` when the final stated goal has an explicit final proof artifact.

## Common commands

Initialize a campaign:

```bash
./run.sh init \
  --campaign refactor-harness-e2e \
  --goal "Finish scoped refactor harness E2E proof"
```

Mark a gate as running:

```bash
./run.sh update \
  --campaign refactor-harness-e2e \
  --state running \
  --current-step "Run hardened concurrent LLM + OpenCode summarize gate"
```

Record a scoped passing gate:

```bash
./run.sh gate-passed \
  --campaign refactor-harness-e2e \
  --label "A01-A18 hardened concurrent LLM + OpenCode summarize" \
  --verdict PASS_SPEC \
  --proof ".plan-iterate/refactor-harness-e2e/proof/refactor-concurrent-mixed.json" \
  --next-action "Start reviewer packet + reviewer fan-in phase" \
  --not-proven "Transport Room B1 UI" \
  --not-proven "build_review_packet reviewer fan-in" \
  --not-proven "Full OpenCode message delivery"
```

Ask the human for a decision:

```bash
./run.sh needs-human \
  --campaign refactor-harness-e2e \
  --question "Which next campaign should the agent run?" \
  --option "A=Continue harness: reviewer packet + reviewer fan-in" \
  --option "B=Transport UI: start Transport Room B1" \
  --option "C=Stabilize only: checkpoint and stop"
```

Render the status page again:

```bash
./run.sh render --campaign refactor-harness-e2e
```

## Anti-dashboard-theater rules

1. No percentages.
2. No green “complete” unless final goal proof exists.
3. Every PASS must name its proof artifact.
4. Every status must show what is not proven.
5. Every idle state must say why the agent is idle.
6. Every human-wait state must include a decision menu.
7. Every blocked state must name the missing artifact, service, gate, or decision.
8. Auto-refresh is allowed only if the page reads `status.json`.
9. If `status.json` is stale, the page must say stale.
10. Reviewer verdicts are receipts, not completion proof.

## When to use

Use this for:

- `/plan-iterate`
- `/orchestrate`
- `/review-design`
- `/review-code`
- `/debugger`
- `/ask deep-review`
- `/code-runner`
- `/subagent-runner`
- any multi-step project-agent work lasting more than one focused command

## Artifact expectations

`status.json` is the source of truth.

`events.jsonl` is append-only and records state transitions.

`proof_manifest.json` lists proof artifacts named by status claims.

`STATUS.html` is generated, stale-aware, and safe to open in a browser.

## Completion standard

A final answer for long-running agent work should summarize the current status
artifact and link or quote the `STATUS.html` path when available.

Do not claim completion unless:

- state is `done`;
- `last_completed.proof_path` points to a final proof artifact;
- `not_proven` is empty or explicitly out of scope;
- blockers are empty.
