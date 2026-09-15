---
name: project-watchdog
description: Simple cron-driven GitHub ticket processor using one Pi fixer, one read-only Pi reviewer, trusted proof, and deterministic close or release.
provides:
  - github-ticket-repair
  - editable-watchdog-workflow
composes:
  - agentic-evals
  - triage-error
---

# project-watchdog V2

Simple unattended GitHub ticket repair loop.

Path per tick:

`cron -> flock -n -> deterministic one-ticket selection -> owned lease -> one Pi native fixer-then-reviewer workflow -> deterministic proof -> close on success OR release owned lease and cooldown on failure -> one receipt`

Cron owns timing only. This skill owns selection, lease, proof, close/release, cooldown, and receipts. Pi subagents owns the fixer-reviewer sequence. The controller reads the native workflow result, including explicit `COMPLETE` and `PASS` statuses, before running proof.

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

## Workflow editor

The active workflow is `workflows/watchdog-v2.json`. Scheduled ticks read this file only. The draft is `workflows/watchdog-v2.draft.json`; editing it does not change scheduled behavior. The graph has one writing `fixer`, one final read-only `reviewer`, and up to ten optional read-only steps. Dependencies must form an acyclic path into the final reviewer.

Open the hot-reloading UX Lab editor at `http://localhost:3002/watchdog` with the UX Lab API running. On this machine port 3001 belongs to Sparta Explorer, so start the API with `PORT=3101 npm run dev:api --workspace ux-lab` and the UI with `UX_LAB_API_PORT=3101 npm run dev:ui --workspace ux-lab` from the `pi-mono` root. The local API delegates to this skill's CLI. The editor can amend tasks and dependencies, save a revision-checked draft, validate its native Pi script, run a throwaway Git sandbox, inspect node results and transcripts, rerun a pinned graph snapshot, and promote a successful exact draft. Promotion requires both draft and active revisions and never occurs during save or sandbox run.

```bash
skills/project-watchdog/run.sh workflow get --source draft
skills/project-watchdog/run.sh workflow validate --source draft --native
skills/project-watchdog/run.sh workflow sandbox-run --source draft --revision SHA256
skills/project-watchdog/run.sh workflow runs
skills/project-watchdog/run.sh workflow run RUN_ID
skills/project-watchdog/run.sh workflow transcript RUN_ID NODE_ID
skills/project-watchdog/run.sh workflow rerun RUN_ID
skills/project-watchdog/run.sh workflow promote RUN_ID --draft-revision SHA256 --active-revision SHA256
```

Native validation checks the script shape, not model availability or task success. A rerun executes the saved graph again in a new sandbox; LLM output is not deterministic. Sandbox receipts, Pi event logs, child transcripts, and throwaway repositories are retained under `~/.local/state/project-watchdog-v2/`. These local runs do not admit, lease, relabel, or close a GitHub issue.

The controller resolves `pi` outside project `node_modules/.bin` paths and pins nested Pi launches to that executable through `PI_SUBAGENT_PI_BINARY`, so an older workspace-local package cannot shadow the installed runtime. Set `PROJECT_WATCHDOG_PI_BIN` to an executable absolute path to override that selection.
