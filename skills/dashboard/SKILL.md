---
name: dashboard
description: >
  Unified Embry OS development dashboard. Aggregates daemon health, LLM metrics,
  shadow agreement, cascade state, skill health, active tasks, Chutes quota, and
  project-state into a single Rich TUI, JSON, or plain-text view.
triggers:
  - /dashboard
  - show me the dashboard
  - system status overview
allowed-tools: [Bash, Read]
metadata:
  short-description: Unified dev dashboard with TUI, JSON, and text output modes.
  version: "0.1.0"
provides:
  - dashboard
composes:
  - project-state
  - service-status
  - ops-chutes
  - task-monitor
  - monitor-skill-health
taxonomy:
  - observability
  - developer-tools
disciplines:
  - observability-operations
  - ui-design-engineering
---

# Dashboard Skill

Unified development dashboard for Embry OS. Aggregates data from 8 independent
collectors into a live Rich TUI, JSON blob, or plain-text summary.

## Usage

```bash
# Live TUI (default) - refreshes every 5s
./run.sh

# JSON output (pipeable to /create-figure)
./run.sh json

# Plain text summary
./run.sh text
```

## Data Sources

| Collector | Source |
|-----------|--------|
| Daemon Health | `state.sock /health/all` |
| LLM Metrics | `~/.pi/assistant/metrics.jsonl` |
| Shadow Agreement | `~/.pi/assistant/shadow.jsonl` |
| Cascade State | `skills/assistant/model_registry.json` |
| Skill Health | `~/.pi/monitor-skill-health/latest_summary.json` |
| Active Tasks | `~/.pi/task-monitor/registry.json` |
| Chutes Quota | `ops-chutes/run.sh usage --json` |
| Project State | `project-state/run.sh report --quick --json` |

## Architecture

- `collectors.py`: 8 independent data fetchers, `collect_all()` via `ThreadPoolExecutor(max_workers=6)`
- `tui.py`: Rich `Live` display with `Layout`/`Panel`/`Table` (same pattern as task-monitor)
- `renderer.py`: JSON and plain-text output modes
- `dashboard.py`: Typer CLI entry point
