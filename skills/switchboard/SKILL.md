---
name: switchboard
description: >
  Standalone deterministic manifest executor via the Switchboard service.
  Steps are subprocess-based (run_command, check_file, check_metrics, call_api) —
  no agent reasoning in the execution path. The project agent supervises via
  structured WebSocket events. Independent of /orchestrate.

triggers:
  - switchboard
  - dispatch to switchboard
  - run through switchboard
  - launch worker
  - supervise run
  - manifest run

allowed-tools: [Bash, Read, Write, Glob, Grep]

metadata:
  short-description: "Deterministic manifest execution via Switchboard"
  author: "Graham + Horus"
  version: "1.0.0"

provides:
  - manifest-execution
  - run-dispatch
  - run-supervision
  - structured-events

composes:
  - memory
  - scillm

taxonomy:
  - orchestration
  - runtime
  - supervision
disciplines:
  - agentic-orchestration
  - observability-operations
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /switchboard

Standalone deterministic manifest executor. Run subprocess steps with structured
WebSocket events and a control plane (pause, cancel, status).

## When to use

Use `/switchboard` for **simple sequential manifest runs** where you have a list of
shell commands to execute with postcondition gates. No DAG scheduling, no LLM reasoning,
no retry loops — just subprocess dispatch with event streaming.

For complex task DAGs with code-runner, blind eval, and strategy escalation, use
`/orchestrate` directly (it calls code-runner via subprocess, no switchboard needed).

## Architecture

```
manifest.yaml → /switchboard → Switchboard server → subprocess execution
                                      ↓
                             structured events via WebSocket
                                      ↓
                             project agent supervises
```

The Switchboard server (`packages/switchboard`) runs the deterministic executor.
Each manifest step maps to a subprocess call. No LLM reasoning in the execution path.

## How it works

1. `/orchestrate` compiles a manifest with steps
2. `/switchboard` POSTs the manifest to `http://127.0.0.1:7890/run/start`
3. Switchboard executes steps sequentially via subprocess
4. Each step emits structured events: `step.started`, `step.completed`, `step.failed`
5. Progress is written to JSONL log files
6. Project agent polls `/run/{run_id}` for status or tails WebSocket events
7. Run completes or fails — project agent makes final synthesis

## Supported action types

| Action | Executor | Use case |
|--------|----------|----------|
| `run_command` | `bash -lc` subprocess | Training, scripts, tests |
| `check_file` | Direct file read | Verify outputs exist |
| `check_metrics` | JSON parse + threshold | Gate on accuracy, F1 |
| `call_api` | HTTP POST | scillm calls, memory learn |
| `open_url`, `click` | **Blocked** — needs agent | Browser automation (future) |

Unsupported actions return `step.blocked` so the project agent can decide what to do.

## Manifest format

```yaml
version: 1
run_id: clf_experiment_001
worker_id: local-executor
steps:
  - step_id: step_01
    label: "Train distilbert on ag_news"
    action:
      type: run_command
      command: "python train.py --model distilbert --epochs 3 --lr 2e-5"
      cwd: "/path/to/working/dir"
    timeout_seconds: 1200
    postcondition:
      type: file_exists
      path: "/tmp/results/result.json"

  - step_id: step_02
    label: "Check accuracy gate"
    action:
      type: check_metrics
      file_path: "/tmp/results/result.json"
    postcondition:
      type: metric_gate
      metric: accuracy
      threshold: 0.95

  - step_id: step_03
    label: "Get HP suggestions from scillm"
    action:
      type: call_api
      url: "http://localhost:4001/v1/chat/completions"
      command: '{"model":"text","messages":[{"role":"user","content":"..."}]}'
    timeout_seconds: 30
```

## Commands

```bash
# Start the Switchboard server
./run.sh server-start

# Check server health
./run.sh health

# Submit a manifest for execution
./run.sh start manifests/my_run.yaml

# Check run status
./run.sh status <run_id>

# Cancel a run
./run.sh cancel <run_id>

# Pause a run
./run.sh pause <run_id>

# List all runs
./run.sh list

# Tail run events (JSONL log)
./run.sh tail <run_id>
```

## Relationship to /orchestrate

Switchboard and orchestrate are **independent executors** for different use cases:

| | /orchestrate | /switchboard |
|---|---|---|
| **Input** | Plan YAML (DAG) | Manifest YAML (sequential) |
| **Scheduling** | DAG with dependencies | Sequential steps |
| **LLM tasks** | code-runner, scillm | call_api (one-shot only) |
| **Retry/escalation** | Yes (blind eval, strategy) | No |
| **Events** | File-based (.events.jsonl) | WebSocket real-time |
| **Control** | PAUSE/KILL files | pause/cancel API |

They do not compose. Use orchestrate for code tasks, switchboard for deterministic scripts.

## Events (via WebSocket)

Connect to `ws://127.0.0.1:7890?agent=supervisor` to receive:

| Event | Data |
|-------|------|
| `run.started` | `{run_id, steps: count}` |
| `step.started` | `{run_id, step_id, label, action_type}` |
| `step.completed` | `{run_id, step_id, duration, metrics}` |
| `step.failed` | `{run_id, step_id, error, exit_code, stderr}` |
| `step.blocked` | `{run_id, step_id, error}` |
| `progress` | `{run_id, step_id, ...parsed JSONL from subprocess}` |
| `run.completed` | `{run_id, steps_completed, steps_failed}` |
| `run.failed` | `{run_id, steps_completed, steps_failed}` |
| `run.cancelled` | `{run_id}` |

## What this skill does NOT do

- Plan or decompose tasks (that's `/plan`)
- Compile manifests from task files (that's `/orchestrate`)
- Agent-mediated execution (subagents are unreliable at 35%)
- Make the executor the brain (the project agent supervises)

## Why not subagent-service?

Tested 2026-03-27: 3 subagent-service Docker containers received prompts, streamed
SSE events (agent was "alive"), but 0/3 wrote any files or executed any training code.
The agent layer between "run this" and "actually running it" is the failure point.

The deterministic executor removes that layer. Subprocess calls run directly.
The Switchboard server provides the control plane (events, pause, cancel) without
the agent overhead.
