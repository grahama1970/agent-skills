---
name: subagent-runner
description: >
  PTY-managed subprocess runner for full CLI agent sessions with transcript capture,
  attach/detach, and intervention controls. Use when a task needs a real terminal-bound
  Codex-class session rather than /code-runner's deterministic bounded edit loop.
triggers:
  - subagent runner
  - pty runner
  - run a codex session in a terminal
  - attach to agent session
  - detached codex run
  - terminal agent session
provides:
  - pty-agent-session
  - session-lifecycle
  - transcript-capture
composes:
  - orchestrate
  - codex
  - task-monitor
read_before_use:
  - models.py
  - session_store.py
  - run.py
  - run.sh
taxonomy:
  - execution
  - orchestration
  - resilience
disciplines:
  - agentic-orchestration
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Subagent Runner

`/subagent-runner` is the PTY-managed runner for real CLI agent sessions.

It is for tasks that need:
- a real terminal-bound subprocess
- transcript capture while the session is still running
- attach/detach and mid-run intervention
- machine-readable session state outside the terminal itself

It is not a replacement for `/code-runner`.

## Use `/code-runner` instead when

- the task is a bounded code change
- the file scope is known ahead of time
- the task has a deterministic Definition of Done
- blind verification or T0 scoring is the main requirement

## Use `/subagent-runner` when

- the task semantics require a real PTY session
- the controller or human may need to attach mid-run
- the task benefits from terminal-native exploration
- transcript and lifecycle artifacts matter as much as the final diff

## Session contract

Every run owns one session directory with canonical artifacts:
- `spec.json`
- `status.json`
- `events.jsonl`
- `commands.jsonl`
- `transcript.log`
- `prompt.txt`
- `result.json`

The typed contract for these artifacts lives in `models.py` and `session_store.py`.

## Current runner status

The runner currently provides:
- typed task/session/result models
- canonical artifact-path ownership
- detached watcher-managed PTY execution
- transcript capture while the subprocess is live
- lifecycle commands for attach, input, pause, resume, cancel, and status

## Commands

```bash
./run.sh help
./run.sh layout
./run.sh start spec.json
./run.sh status <session-dir-or-id>
./run.sh attach <session-dir-or-id>
./run.sh send-input <session-dir-or-id> "text"
./run.sh pause <session-dir-or-id>
./run.sh resume <session-dir-or-id>
./run.sh cancel <session-dir-or-id>
```

## Safety constraints

Even with a PTY, the runner must keep:
- explicit working directory
- explicit output directory
- machine-readable status outside the subprocess
- observable intervention state
- no silent fallthrough on failed session setup
