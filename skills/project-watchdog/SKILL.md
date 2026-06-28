---
name: project-watchdog
description: >
  Global cross-project watchdog registry and dispatcher contract for scanning
  GitHub issues, selecting bounded subagents, and invoking each project's Tau
  or project-local harness one ticket at a time.
allowed-tools:
  - Bash
  - Read
  - Grep
triggers:
  - project watchdog
  - global watchdog
  - github issue cron
  - cross-project cron
  - project registry
metadata:
  short-description: Cross-project GitHub issue watchdog registry
provides:
  - task-orchestration
  - progress-tracking
  - ticket-lookup
  - ticket-lease-routing
  - ticket-resolution
composes:
  - tau
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-subagent
  - best-practices-github-ticket
---

# Project Watchdog

`project-watchdog` is the shared control-plane location for a future global
GitHub issue watchdog. It keeps the cross-project registry next to the shared
skills and subagents so individual projects do not each invent their own cron
loop.

The intended runtime is deliberately narrow:

1. Load `registry/projects.json`.
2. Scan registered GitHub repos for routable issues.
3. Acquire one lease for one project ticket.
4. Invoke the project runner for one bounded tick.
5. Require a receipt.
6. Post the receipt or refusal back to GitHub.
7. Exit or move to the next project within the configured ticket limit.

The watchdog must not perform unbounded repair, invent missing routing, or make
global completion claims. If routing is missing or unauthorized, it should label
the issue for `next:human` or the project equivalent and stop.

## Registry

Project entries live in:

```text
registry/projects.json
registry/state.json
```

Each entry describes the project worktree, GitHub repo, allowed local agent
root, and the project-local command that should perform one bounded tick.

`projects.json` is relatively static configuration. `state.json` is the
operator-controlled runtime gate for pause, stop, and resume decisions.

The registry is a contract artifact only until a runtime dispatcher is added. Do
not treat a registry entry as proof that the project is currently monitored.

## Pause, Stop, Resume

The watchdog must check both global and per-project state before scanning or
dispatching. State is fail-closed:

- `active`: scanning and one bounded dispatch are allowed.
- `paused`: observation is allowed; dispatch and mutation are refused.
- `stopped`: the project is ignored except for a trusted human resume action.

Subagents may request pause or stop in their receipt, but they do not own the
state transition unless the project explicitly grants that authority. A normal
worker request should become a GitHub comment or watchdog receipt requiring
human/operator confirmation.

Resume should require a trusted human/operator action and any project-specific
preconditions listed in `resume_requires`, such as a valid goal capsule, clean
worktree, or valid GitHub authentication.

## Dynamic GitHub Actions

GitHub Actions and the local watchdog should cooperate through labels and
receipts, not by racing each other:

- `executor:github-actions`: cloud-safe validation, lint, tests, and read-only
  review can run in Actions.
- `executor:local`: WebGPT, local browser, mounted storage, local models, and
  private workstation services must be picked up by the local watchdog.
- `executor:either`: the watchdog may choose based on project policy and current
  lease state.

Actions may route work to local by commenting a schema-valid handoff and
changing labels to `executor:local`. The local watchdog may route work to
Actions by invoking `workflow_dispatch` or `repository_dispatch` only when the
project config declares the workflow as allowed.

No dispatcher should mutate an issue unless it holds the current lease.

## Tau Generic Handoff Issue Marker

Tau issues can be routed through the global watchdog by adding `agent-work`,
`executor:local`, and a body marker:

```text
project-watchdog-action:tau-handoff-dispatch \
  start=experiments/goal-locked-subagents/proofs/.../start-handoff.json \
  max_steps=1 \
  active_goal_hash=sha256:... \
  apply_transport=false
```

The watchdog treats `start` as a Tau repo-relative path, rejects absolute paths
or `..`, runs one bounded `tau handoff-command-loop` tick, writes receipts under
`~/.local/state/project-watchdog/receipts/<run_id>/`, and comments the evidence
back to the issue. `apply_transport=true` is allowed only when the issue should
apply the terminal Tau GitHub transport; otherwise the transport receipt is
rendered dry-run.

Issues with `agent-active` or `agent-blocked` are skipped until a human/operator
clears the state label. This prevents cron from retrying a failed ticket every
minute without an explicit retry decision.
