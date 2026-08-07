# herdr-workstation

> **Disciplines:** agentic-orchestration · observability-operations

`herdr-workstation` is a skill for turning long-running project-agent work into visible Herdr workstations.

It is designed for the pattern we discussed:

```text
one long-running task
  -> one Herdr workspace
  -> tabs: agents, logs, receipts
  -> panes: Qbert/Codex, Petey/OpenCode, Dewey/Claude, validator shell
  -> live messages through Herdr
  -> durable work orders and receipts as truth
```

## Why this exists

Hidden background subagents are hard to trust and hard to recover. Herdr makes the live execution visible, while the project agent keeps deterministic receipts and policy gates.

Use this skill when a main project agent needs to:

- create a dynamic Herdr workspace per task
- start different provider agents in separate panes
- send instructions directly to a named pane/agent
- read recent pane output
- wait for an agent state
- report custom role state like `Petey: reviewing` or `Qbert: blocked`
- remove the workspace or worktree after completion
- run bounded creator/reviewer batches with receipt files

## Install dependencies

```bash
cd skills/herdr-workstation
uv sync
```

## Quick start

```bash
./run.sh doctor
./run.sh install-integrations codex opencode claude
```

Create a task workstation:

```bash
./run.sh workstation create \
  --repo ~/agent-skills \
  --label ms-qra-gap-1842 \
  --tab agents \
  --tab logs \
  --tab receipts
```

Start provider-specific panes:

```bash
MANIFEST=.herdr-workstations/<run-id>/workstation.json

./run.sh agent start "$MANIFEST" \
  --name qbert-codex \
  --role qbert \
  --command codex

./run.sh agent start "$MANIFEST" \
  --name petey-opencode \
  --role petey \
  --command opencode \
  --split right
```

Send instructions:

```bash
./run.sh agent send qbert-codex \
  --text 'Read .runs/1842/work-orders/qbert.md and stay blocked until Petey writes PASS.'

./run.sh agent read petey-opencode --lines 120
```

Report state from inside a pane:

```bash
./run.sh agent report \
  --agent Qbert \
  --state blocked \
  --custom-status waiting-petey-pass
```

Remove the workstation:

```bash
./run.sh workstation remove "$MANIFEST"
```

## Batch creator/reviewer loop

```bash
./run.sh batch creator-reviewer \
  --repo ~/agent-skills \
  --tasks references/example_loop_tasks.json \
  --creator-cmd codex \
  --reviewer-cmd opencode \
  --concurrency 2
```

The batch command creates one Herdr workstation per task and waits for receipt JSON files written by the agents.

## Source of truth

Herdr is not the approval registry. The truth is still:

- work orders
- handoff files
- creator receipts
- reviewer receipts
- final JSON
- project-specific approval rows

Herdr provides visibility, live control, and recoverability.
