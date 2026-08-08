---
name: task-monitor
description: >
  Monitor long-running tasks with Rich TUI and HTTP API. Includes scheduler integration and auto-restart.
allowed-tools: Bash, Read
triggers:
  - monitor tasks
  - check task progress
  - task status
  - start task monitor
metadata:
  short-description: Task monitoring TUI, API, and Scheduler
provides:
  - progress-tracking
composes:
  - memory
  - scheduler
  - task-monitor
  - agentic-evals
taxonomy:
  - observability
  - orchestration
disciplines:
  - observability-operations
  - agentic-orchestration
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Task Monitor Skill

nvtop-style Rich TUI and HTTP API for monitoring long-running tasks across projects.
Integrated with **Scheduler** to show upcoming jobs.

## CRITICAL: Agent Watchdog Pattern

**When starting ANY long-running task (LLM batch, extraction, embedding, etc.), agents MUST:**

1. **Start a session**: `uv run python monitor.py start-session --project <project>`
2. **Register the task**: `uv run python monitor.py register --name <task> --state <file> --total <n>`
3. **Set up a watchdog timer loop** that runs every 30-60 seconds:
   - Parse log/state for progress
   - Validate LLM response quality (check for invalid outputs)
   - Update task-monitor state via API
   - **STOP and DEBUG** if errors exceed threshold
   - Alert on stalls (no progress for 5+ minutes)
4. **Run quality checks** using `/quality-audit` or `/batch-quality` skills
5. **End session** with accomplishments when complete

**Example Watchdog Loop:**
```python
while task_running:
    metrics = parse_log()           # Get progress, errors
    validate_outputs(metrics)       # Check LLM response quality
    update_task_monitor(metrics)    # Push to API
    if metrics.errors > THRESHOLD:
        stop_and_debug()            # Don't let bad data accumulate
    if stalled(metrics):
        alert("Stall detected")
    time.sleep(30)
```

**This is NOT optional.** Agents that skip monitoring waste tokens on bad extractions.

---

## Features

- **Rich TUI** - Real-time terminal UI with progress bars, rates, ETAs, and **Scheduler** panel.
- **Python Adapter** - Drop-in `tqdm` replacement (`Monitor`) for easy integration.
- **HTTP API** - FastAPI endpoints for cross-agent monitoring (Pull & Push).
- **Task Registry** - Global registry at `~/.pi/task-monitor/registry.json`.
- **Filtering** - Filter visible tasks by name.
- **Auto-Restart** - Systemd service integration.

## Quick Start

```bash
cd .pi/skills/task-monitor

# Start TUI (interactive)
uv run python monitor.py tui

# Filter specific tasks
uv run python monitor.py tui --filter youtube

# Start API server
uv run python monitor.py serve --port 8765
```

## Python Integration (Adapter)

Use the `Monitor` class to wrap iterables (like `tqdm`). automatically updating the monitor state.

```python
from monitor_adapter import Monitor

# Local Mode (updates .batch_state.json)
for item in Monitor(items, name="my-task", total=1000):
    process(item)

# Remote Mode (pushes to API)
for item in Monitor(items, name="my-task", api_url="http://localhost:8765"):
    process(item)
```

## Scheduler Integration

The TUI automatically reads `~/.pi/scheduler/jobs.json` and displays an "Upcoming Schedule" panel showing:

- Job Name
- Cron Schedule
- Next Run Time
- Status (Active/Disabled)

## Commands

### Register a Task

```bash
uv run python monitor.py register \
    --name "youtube-luetin09" \
    --state /path/to/.batch_state.json \
    --total 1946 \
    --project my-project
```

### List & Status

```bash
uv run python monitor.py list
uv run python monitor.py status
```

### History & Resume ("Where Was I?")

```bash
# Show where you left off
uv run python monitor.py history resume

# Search history by task/project
uv run python monitor.py history search sparta

# Show recent history
uv run python monitor.py history recent

# Show history for a project
uv run python monitor.py history project my-project

# List work sessions
uv run python monitor.py history sessions
```

### Session Tracking

```bash
# Start a work session
uv run python monitor.py start-session --project sparta

# Add accomplishment
uv run python monitor.py add-accomplishment "Completed stage 05 extraction"

# End session
uv run python monitor.py end-session --notes "Paused for review"
```

### Start TUI

```bash
uv run python monitor.py tui [--filter youtube] [--refresh 2]
```

### Start API Server

```bash
uv run python monitor.py serve --port 8765
```

## HTTP API Endpoints

| Endpoint              | Method | Description                       |
| --------------------- | ------ | --------------------------------- |
| `/all`                | GET    | Get status of all tasks + totals  |
| `/tasks/{name}`       | GET    | Get status of specific task       |
| `/tasks/{name}/state` | POST   | **Push** state update (JSON body) |
| `/tasks`              | POST   | Register a new task               |

## Auto-Restart (Systemd)

To install the API and Scheduler as systemd services (auto-restart on crash):

```bash
# Run the installation script
./install_services.sh
```

This creates user-level systemd units:

- `pi-task-monitor.service`
- `pi-scheduler.service`

Manage them with:
`systemctl --user status pi-task-monitor`
`systemctl --user restart pi-scheduler`

## Discord Integration (Mobile Monitoring)

Push task updates to Discord for monitoring from iPad/iPhone.

### Setup

1. Create a Discord webhook in your server (Server Settings > Integrations > Webhooks)
2. Set the environment variable:
   ```bash
   export TASK_MONITOR_DISCORD_WEBHOOK="https://discord.com/api/webhooks/..."
   ```

### Commands

```bash
# Test webhook connection
uv run python discord_publisher.py test

# Post current status (text embed)
uv run python discord_publisher.py post-status

# Post visual dashboard (with chart image)
uv run python discord_publisher.py post-dashboard

# Start daemon (auto-posts on changes + periodic dashboards)
uv run python discord_publisher.py daemon --interval 300
```

### Daemon Mode

The daemon posts:
- **Real-time**: Text updates on task completion or errors
- **Periodic**: Visual dashboard every N seconds (default: 300s / 5min)

```bash
# Start as background service
nohup uv run python discord_publisher.py daemon --interval 300 > /tmp/task-monitor-discord.log 2>&1 &
```

### Dashboard Features

- Progress bars per task
- Color-coded status (green=done, blue=running, red=errors)
- Dark theme matching Discord
- Timestamps

## Architecture

- **Registry**: `~/.pi/task-monitor/registry.json` (Global)
- **State Files**: tasks update their own JSON files (or push to API).
- **Monitor**: Polls state files (or receives pushes) and displays TUI.
- **Discord Publisher**: Webhook-based push to Discord channels.

## Common Mistakes

```bash
# WRONG: Spawn long-running task without registering
subprocess.run([".pi/skills/extractor/run.sh", "*.pdf", "--accurate"])
# → No progress tracking, no error detection, wasted 500+ API tokens on bad OCR
# RIGHT: Register task, watchdog loop every 30s
./run.sh register --name "extract-batch" --state .batch_state.json --total 100

# WRONG: Schedule job without checking daemon is running
./run.sh register --name "nightly" --cron "0 2 * * *" --command "..."
# → Job written to disk but daemon crashed — never executes
# RIGHT: Check status first
./run.sh status | grep "running" || ./run.sh start

# WRONG: No stall detection on monitored tasks
# → Task stalls at 45%, agent waits forever
# RIGHT: Set timeout in watchdog, escalate if no progress in 5min
```
