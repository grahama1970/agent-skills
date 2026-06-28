---
name: tau
description: >
  Operate and verify the local T'au project at /home/graham/workspace/experiments/tau.
  Use for Tau loop, harness, watchdog cron, GitHub issue orchestration, TUI,
  Memory-first chat, and E2E proof/status tasks. This skill is a light wrapper
  around the Tau repo and must report mocked/live proof boundaries explicitly.
triggers:
  - tau
  - t'au
  - tau loop
  - tau harness
  - tau watchdog
  - tau tui
  - tau chat
  - verify tau
  - tau e2e sanity
provides:
  - task-orchestration
  - progress-tracking
  - ticket-lease-routing
  - proof-based-closure
composes:
  - memory
  - project-watchdog
  - test-interactions
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-subagent
  - best-practices-react
runtime_self_improvement: basic
taxonomy:
  - validation
  - resilience
  - orchestration
---

# Tau

Use this skill as the operator entrypoint for the local T'au project:

```text
/home/graham/workspace/experiments/tau
```

Do not duplicate Tau implementation in this skill. Use the scripts here to
locate the repo, run known proof commands, inspect receipts, and summarize gaps.

## Commands

```bash
skills/tau/run.sh status
skills/tau/run.sh sanity
skills/tau/run.sh e2e
skills/tau/run.sh watchdog-status
skills/tau/run.sh latest-proofs
```

`status` reports current repo, GitHub issue, watchdog cron, and latest receipt
state. `sanity` runs bounded checks that do not mutate GitHub. `e2e` runs the
same checks plus recent live-proof inspection; it does not create or close new
GitHub issues.

## Proof Rules

- State `mocked` and `live` boundaries for every result.
- Unit tests are not E2E proof.
- Loop and harness claims require fresh command-loop/watchdog receipts.
- TUI claims require targeted Textual/TUI checks.
- Chat UI claims require browser/CDP screenshot verification from the host app.
- Chat UI interaction manifests must follow `test-interactions`: live DOM
  `[data-qid]` selectors only, deterministic assertions, and no fake fixtures
  for production claims.
- React chat changes must follow `best-practices-react`: interactive elements
  need `data-qid`, `data-qs-action`, `title`, and host action registration.
- Subagent handoffs must use `tau.agent_handoff.v1`.
- Human goal changes must use `tau.human_goal_change.v1`; non-human agents may
  propose but not apply immutable goal changes.

## Key Artifacts

```text
/home/graham/.local/state/project-watchdog/logs/cron.log
/home/graham/.local/state/project-watchdog/logs/project-watchdog.log
/home/graham/.local/state/project-watchdog/receipts/
/home/graham/workspace/experiments/tau/experiments/goal-locked-subagents/proofs/
/home/graham/workspace/experiments/tau/ui/tau-chat-contract.json
```

Use `agents/tau` for Tau-specific bounded worker turns when a global watchdog or
project agent needs a named subagent identity.

## Project Knowledge

Read `/home/graham/workspace/experiments/tau/PROJECT_KNOWLEDGE.md` before making claims about current Tau
coverage. It records which proof lanes have local evidence and which remain
pending.
