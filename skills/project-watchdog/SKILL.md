---
name: project-watchdog
description: Simple cron-driven GitHub ticket processor using one Pi fixer, one read-only Pi reviewer, trusted proof, and deterministic close or release.
---

# project-watchdog V2

Simple unattended GitHub ticket repair loop.

Path per tick:

`cron -> flock -n -> deterministic one-ticket selection -> owned lease -> Pi native subagents fixer -> Pi native subagents read-only reviewer -> deterministic proof -> close on success OR release owned lease and cooldown on failure -> one receipt`

Cron owns timing only. This skill owns selection, lease, proof, close/release, cooldown, and receipts. Pi subagents own the fixer and reviewer.

## CLI

```bash
skills/project-watchdog/run.sh status
skills/project-watchdog/run.sh tick [--apply] [--project ID|all]
skills/project-watchdog/run.sh set-state active|paused [--scope global|project] [--project ID] [--reason TEXT]
skills/project-watchdog/run.sh install-cron [--apply]
skills/project-watchdog/scripts/stream-view.sh
```

- Default global state is paused.
- Without `--apply`, no GitHub mutation and no Pi subagent launch occur.
- `--project ID` is strict. `--project all` rotates active projects deterministically.
- Quiet outcomes (`NOOP`, paused, overlap, cooldown, dry run) print JSON and write no receipt.
- Eventful success/failure writes exactly one receipt under `~/.local/state/project-watchdog-v2/receipts/`.

## Failure handling

Every V2 boundary failure is classified through `skills/triage-error/run.sh classify`. Receipts persist the classifier command/output plus canonical `code`, `cause`, and `next_command` when classification succeeds. If classification fails, the receipt preserves the classifier command/output and fails closed.

Human hold labels are never removed. Fixer, reviewer, proof, close, or triage failure leaves the issue open, releases only the owned lease when safe, and sets cooldown.
