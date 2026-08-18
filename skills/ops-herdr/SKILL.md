---
name: ops-herdr
description: >
  Use this skill when a project agent needs to spin up, inspect, communicate with,
  or remove Herdr-managed workstations for long-running multi-agent tasks. It
  provides a Typer CLI for dynamic Herdr workspaces, provider-specific agent panes,
  pane-to-pane notifications, semantic role state reporting, and bounded
  creator/reviewer loops with durable receipts.
triggers:
  - herdr workstation
  - herdr subagents
  - visible subagent loop
  - dynamic herdr workspace
  - spin up herdr workspaces
  - communicate with herdr agent
  - petey qbert dewey herdr
  - creator reviewer loop herdr
  - ops herdr
  - herdr operations
provides:
  - ops-herdr-orchestration
  - visible-subagent-runtime
  - dynamic-agent-workspaces
  - pane-agent-communication
  - creator-reviewer-loop-runtime
composes:
  - best-practices-python
  - best-practices-skills
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
runtime_self_improvement: basic
taxonomy:
  - orchestration
  - progress-tracking
  - agent-runtime
  - receipts
  - terminal-control
disciplines:
  - agentic-orchestration
  - observability-operations
---

# Herdr Ops

Use this skill when subagent work should be visible, attachable, and recoverable in Herdr instead of hidden in opaque background jobs.

## Boundary

Herdr is the live terminal/session fabric. It manages workspaces, tabs, panes, provider agents, agent state, pane reads, and pane input.

The project agent, T'au, monitor-sparta, or the calling workflow remains the source of truth for queue selection, policy gates, receipts, review verdicts, and final PASS/BLOCKED decisions.

Do not use Herdr chat as the canonical approval record. Use Herdr messages as live instructions or notifications; require durable work orders, receipts, and final JSON.

## When to use

Use Herdr workstations for long-running or multi-agent tasks where progress visibility and intervention matter:

- creator/reviewer loops
- Petey/Qbert/Dewey style monitor-sparta work
- prompt-health approval gates
- QRA generation with reviewer approval
- live validators, logs, and receipt tailing
- tasks that may block and need human/project-agent steering

Use headless execution for tiny deterministic helpers, one-shot transforms, and short validators.

## Commands

Run through the skill wrapper:

```bash
./run.sh doctor
./run.sh workstation create --repo ~/agent-skills --label ms-qra-gap-1842
./run.sh agent start .herdr-workstations/<run>/workstation.json --name qbert-codex --role qbert --command codex
./run.sh agent start .herdr-workstations/<run>/workstation.json --name petey-opencode --role petey --command opencode --split right
./run.sh agent send qbert-codex --file .runs/<run>/work-orders/qbert.md
./run.sh agent read petey-opencode --lines 120
./run.sh agent report --agent Qbert --state blocked --custom-status waiting-petey-pass
./run.sh workstation remove .herdr-workstations/<run>/workstation.json
```

## Durable communication pattern

Preferred subagent coordination:

1. Main project agent writes a work order.
2. Main project agent starts or reuses a Herdr workstation.
3. Main project agent sends the work-order path to the target pane.
4. Subagent writes a receipt or handoff file.
5. Main project agent reads receipt and advances the workflow.

Pane-to-pane messages should be bounded notifications, for example: "handoff ready at path X". They should not replace receipt-backed review.

## Environment guards

Agents running inside Herdr can report semantic state with `HERDR_PANE_ID`. Herdr sets `HERDR_ENV=1`, `HERDR_WORKSPACE_ID`, `HERDR_TAB_ID`, and `HERDR_PANE_ID` inside managed panes. If those are missing, pass `--pane-id` explicitly or do not report pane state.

## Provider panes

A single workstation can run different providers in different panes:

```bash
./run.sh install-integrations codex opencode claude kimi
./run.sh agent start workstation.json --name qbert-codex --role qbert --command codex
./run.sh agent start workstation.json --name petey-opencode --role petey --command opencode --split right
```

## Verification

```bash
./sanity.sh
./run.sh verify
```

`sanity.sh` compiles the Python modules and runs CLI self-checks without requiring a live Herdr server.
