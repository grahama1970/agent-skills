---
name: agent-inbox
description: >
  File-based inter-agent messaging with headless dispatch. Check inbox, send bugs/requests to other projects,
  automatically spawn headless agents to fix bugs, and track progress via task-monitor.
allowed-tools: Bash, Read
triggers:
  - check your inbox
  - check inbox
  - check messages
  - any messages
  - any pending messages
  - agent sent you
  - send message to
  - send bug to
  - dispatch bug fix
  - headless agent
  - spawn agent
  - report bug to
  - cross-project message
  - pending issues
  - pending bugs
metadata:
  short-description: Inter-agent messaging with headless dispatch and task-monitor integration
provides:
  - inter-agent-messaging
  - headless-dispatch
  - triage-routing
composes:
  - task-monitor
  - memory
  - project-state
  - checkpoint
  - scillm
  - ops-discord
  - interview
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Agent Inbox

File-based inter-agent messaging with headless dispatch and task-monitor integration.

## Core Workflow

1. **Send**: Agent A sends bug/request to project B with model + verification command
2. **Triage**: AI classifies severity, adjusts priority/model, routes to project
3. **Dispatch**: Headless agent spawns with specified model to fix the issue
4. **Track**: Task-monitor shows real-time progress (0% → 25% → 50% → 75% → 100%)
5. **Verify**: Test command runs before auto-ack — fails loop back to agent
6. **Thread**: Reply/exchange threading for multi-message conversations

## Setup

```bash
# Register projects (one-time)
.pi/skills/agent-inbox/agent-inbox register memory /home/user/workspace/memory
.pi/skills/agent-inbox/agent-inbox register scillm /home/user/workspace/litellm

# List / check
.pi/skills/agent-inbox/agent-inbox projects
.pi/skills/agent-inbox/agent-inbox whoami
```

## Commands

| Command | Description |
|---------|-------------|
| `register <name> <path>` | Register a project |
| `unregister <name>` | Remove a project |
| `projects [--json]` | List registered projects |
| `whoami` | Show detected project for cwd |
| `send --to PROJECT --type TYPE "msg"` | Send message (types: bug, request, info, question) |
| `check [--project P] [--all] [--quiet]` | Check inbox |
| `list [--project P] [--status S] [--json]` | List messages |
| `read MSG_ID [--json]` | Read a message |
| `ack MSG_ID [--note "..."]` | Acknowledge/complete |
| `reply MSG_ID "msg"` | Reply (auto-threads) |
| `thread THREAD_ID` | View full exchange thread |
| `update-status MSG_ID STATUS [--note]` | Update status manually |
| `triage classify --message "..." [--no-llm]` | Manual triage classification |
| `triage route --message "..."` | Auto-route by file paths |
| `triage log --msg-id ID` | View triage decision log |
| `triage webhook-add --url URL --events E` | Register webhook |

## Send Options

| Option | Description | Default |
|--------|-------------|---------|
| `--model MODEL` | AI model: sonnet, opus-4.5, codex-5.2, codex-5.2-high | sonnet |
| `--timeout MINUTES` | Max agent work time | 30 |
| `--test COMMAND` | Verification command before auto-ack | None |
| `--no-dispatch` | Disable auto-spawn | False |
| `--context-file FILE` | Attach file as context (repeatable) | None |
| `--priority PRIORITY` | low, normal, high, critical | normal |
| `--no-triage` | Skip AI triage | False |
| `--dry-run` | Show message JSON without sending | False |

## Model Selection

| Model | Use Case |
|-------|----------|
| `sonnet` | Simple fixes, typos |
| `opus-4.5` | Complex analysis, architecture |
| `codex-5.2` | Standard bug fixes |
| `codex-5.2-high` | Deep reasoning, race conditions |

## AI Triage

Messages are auto-classified by severity:
- **critical**: crash, data loss, security, production down → `opus-4.5`
- **high**: error, exception, failure, broken, regression → `opus-4.5`
- **medium**: bug, issue, incorrect, unexpected → `sonnet`
- **low**: typo, cosmetic, enhancement, minor → `sonnet`

Auto-routing extracts file paths from messages and matches against registered projects.

## Status Progression

`pending` → `dispatched` (25%) → `in_progress` (50%) → `needs_verification` (75%) → `done` (100%)

## Memory Pre-Hook

Dispatcher queries `/memory` before spawning to find similar bugs and prior solutions.

## Proactive Checking

Agents should check inbox on session start, when switching projects, before major work,
and when users mention another agent or project.

## Storage

```
~/.agent-inbox/
├── pending/          # Unprocessed messages
├── done/             # Acknowledged messages
├── logs/             # Dispatch logs
├── task_states/      # Task-monitor state files
├── triage_logs/      # AI triage decision logs
├── webhooks.json     # Registered webhooks
└── projects.json     # Project registry
```

## Examples

```bash
# Send bug with verification (spawns headless Opus agent, auto-acks if test passes)
python inbox.py send --to scillm --type bug --model opus-4.5 \
  --test "pytest tests/test_providers.py -x" \
  "Race condition in provider initialization"

# Attach context files
python inbox.py send --to scillm --type bug --model opus-4.5 \
  --context-file src/server.py --context-file /tmp/traceback.txt \
  "Server crash on startup"

# Check and process inbox
python inbox.py check --all
python inbox.py read scillm_abc123
python inbox.py ack scillm_abc123 --note "Fixed in commit abc123"

# Threaded exchange
python inbox.py reply scillm_abc123 "Can you provide the stack trace?"
python inbox.py thread scillm_abc123
```

## Dispatcher Daemon

```bash
python dispatcher.py start              # Background
python dispatcher.py start --foreground  # Debug
python dispatcher.py status
python dispatcher.py stop
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_INBOX_DIR` | Inbox directory | `~/.agent-inbox` |
| `TASK_MONITOR_API_URL` | Task-monitor URL | `http://localhost:8765` |
| `CLAUDE_PROJECT` | Current project name | auto-detected |

## Integration with Claude Code Hooks

```json
{
  "hooks": {
    "on_session_start": [
      ".pi/skills/agent-inbox/agent-inbox check --project $(basename $PWD) || true"
    ]
  }
}
```
