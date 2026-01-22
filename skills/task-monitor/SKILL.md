---
name: task-monitor
description: >
  Monitor long-running tasks with Rich TUI and HTTP API. Use when user says "monitor tasks",
  "check progress", "task status", "start monitor", or needs to track batch processing jobs.
allowed-tools: Bash, Read
triggers:
  - monitor tasks
  - check task progress
  - task status
  - start task monitor
  - watch tasks
metadata:
  short-description: Task monitoring TUI and API
---

# Task Monitor Skill

nvtop-style Rich TUI and HTTP API for monitoring long-running tasks across projects.

## Features

- **Rich TUI** - Real-time terminal UI with progress bars, rates, and ETAs
- **HTTP API** - FastAPI endpoints for cross-agent monitoring
- **Task Registry** - Persistent tracking of monitored tasks
- **Rate Calculation** - Rolling 10-minute window for accurate rates
- **Multi-Task** - Monitor multiple independent tasks simultaneously

## Quick Start

```bash
cd .pi/skills/task-monitor

# Register a task to monitor
uv run python monitor.py register \
    --name "my-batch" \
    --state /path/to/state.json \
    --total 1000

# Start TUI (interactive)
uv run python monitor.py tui

# Or start API server
uv run python monitor.py serve --port 8765

# Quick status check
uv run python monitor.py status
```

## Commands

### Register a Task

```bash
uv run python monitor.py register \
    --name "youtube-luetin09" \
    --state /home/graham/workspace/experiments/pi-mono/run/youtube-transcripts/luetin09/.batch_state.json \
    --total 1946 \
    --desc "Luetin09 YouTube transcripts"
```

**Options:**
| Option | Short | Description |
|--------|-------|-------------|
| `--name` | `-n` | Task name (required) |
| `--state` | `-s` | Path to state JSON file (required) |
| `--total` | `-t` | Total items to process |
| `--desc` | `-d` | Task description |

### Unregister a Task

```bash
uv run python monitor.py unregister my-batch
```

### List Tasks

```bash
uv run python monitor.py list
```

### Quick Status

```bash
uv run python monitor.py status
```

Output:
```
youtube-luetin09: 535/1946 (27.5%)
youtube-remembrancer: 183/688 (26.6%)
```

### Start TUI

```bash
uv run python monitor.py tui --refresh 2
```

**Options:**
| Option | Short | Description |
|--------|-------|-------------|
| `--refresh` | `-r` | Refresh interval in seconds (default: 2) |

The TUI shows:
- Task name
- Progress bar with percentage
- Rate (items/hour)
- ETA
- Current item being processed

Press `Ctrl+C` to exit.

### Start API Server

```bash
uv run python monitor.py serve --port 8765
```

## HTTP API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | List available endpoints |
| `/tasks` | GET | List registered task names |
| `/tasks/{name}` | GET | Get status of specific task |
| `/all` | GET | Get status of all tasks with totals |
| `/tasks` | POST | Register a new task |
| `/tasks/{name}` | DELETE | Unregister a task |

### Example API Usage

```bash
# List all tasks
curl http://localhost:8765/tasks

# Get all status with totals
curl http://localhost:8765/all

# Get specific task
curl http://localhost:8765/tasks/youtube-luetin09

# Register task via API
curl -X POST http://localhost:8765/tasks \
    -H "Content-Type: application/json" \
    -d '{"name": "my-task", "state_file": "/path/to/state.json", "total": 100}'
```

### Response Format

```json
{
  "tasks": {
    "youtube-luetin09": {
      "name": "youtube-luetin09",
      "state_file": "/path/to/state.json",
      "total": 1946,
      "completed": 535,
      "progress_pct": 27.5,
      "stats": {"success": 530, "failed": 3, "whisper": 50},
      "current_item": "dQw4w9WgXcQ",
      "current_method": "fetching",
      "last_updated": "2026-01-21 15:30:00",
      "consecutive_failures": 0
    }
  },
  "totals": {
    "completed": 718,
    "total": 2634,
    "progress_pct": 27.3
  }
}
```

## State File Format

The monitor reads JSON state files with these fields:

```json
{
  "completed": ["id1", "id2", "..."],
  "stats": {
    "success": 100,
    "failed": 2,
    "skipped": 0,
    "rate_limited": 0,
    "whisper": 50
  },
  "current_video": "dQw4w9WgXcQ",
  "current_method": "whisper",
  "last_updated": "2026-01-21 15:30:00",
  "consecutive_failures": 0
}
```

Fields are flexible - the monitor adapts to:
- `completed` as array (counts length) or number
- `current_video`, `current_item`, or `current` for current item
- Any additional stats fields

## Integration with Other Skills

### YouTube Transcripts

Register the youtube-transcripts batch jobs:

```bash
cd .pi/skills/task-monitor

# Register Luetin09
uv run python monitor.py register \
    -n "luetin09" \
    -s /home/graham/workspace/experiments/pi-mono/run/youtube-transcripts/luetin09/.batch_state.json \
    -t 1946

# Register Remembrancer
uv run python monitor.py register \
    -n "remembrancer" \
    -s /home/graham/workspace/experiments/pi-mono/run/youtube-transcripts/remembrancer/.batch_state.json \
    -t 688
```

### From Other Agents

Other agents can query the HTTP API:

```python
import httpx

async def check_progress():
    async with httpx.AsyncClient() as client:
        resp = await client.get("http://localhost:8765/all")
        data = resp.json()
        return data["totals"]["progress_pct"]
```

Or use CLI:

```bash
curl -s http://localhost:8765/all | jq '.totals.progress_pct'
```

## Dependencies

```toml
dependencies = [
    "typer",
    "rich",
    "fastapi",
    "uvicorn",
    "httpx",
    "pydantic",
]
```

## Architecture

```
task-monitor/
├── SKILL.md          # This file
├── pyproject.toml    # Dependencies
├── monitor.py        # Main module (TUI + API + CLI)
└── .task_registry.json  # Persistent task registry (auto-created)
```

The monitor:
1. Reads task configs from `.task_registry.json`
2. Polls each task's state file at the refresh interval
3. Calculates rates from a rolling 10-minute history
4. Displays progress in TUI or serves via HTTP API
