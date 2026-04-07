---
name: monitor-claude
description: >
  Continuous Claude Code process health monitor. Detects memory-leaked sessions,
  zombie headless agents, and runaway CPU usage. Fires Discord alerts and optionally
  auto-kills processes exceeding hard limits. Designed to run on a scheduler.
triggers:
  - monitor claude processes
  - check claude memory usage
  - find zombie claude sessions
  - claude process health
  - are any claude sessions leaking memory
  - how many claude processes are running
  - kill stale claude processes
allowed-tools:
  - Bash
  - Read
metadata:
  short-description: Continuous Claude Code process health watchdog
provides:
  - claude-process-monitoring
  - claude-memory-watchdog
  - claude-zombie-detection
composes:
  - ops-claude
  - memory
  - scheduler

taxonomy:
  - monitoring
  - operations
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# monitor-claude

Continuous health watchdog for Claude Code processes. Detects and alerts on:

- **Memory leaks**: Processes with RSS exceeding configurable threshold (default 5 GB)
- **Zombie agents**: Headless processes (no TTY) older than max age (default 4 hours)
- **CPU runaways**: Processes consuming >80% CPU for extended periods
- **Process sprawl**: Total Claude process count exceeding limit (default 15)

## Commands

| Command | Description |
|---------|-------------|
| `scan` | One-shot scan, report findings to stdout |
| `scan --kill` | Scan and auto-kill processes exceeding hard limits |
| `scan --json` | Machine-readable JSON output |
| `watch` | Continuous mode — scan every interval, alert on violations |
| `status` | Quick summary: process count, total RSS, top offenders |
| `history` | Show recent alert history from log |

## Thresholds (configurable via env vars)

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_MAX_RSS_GB` | 5 | Soft alert threshold per process (GB) |
| `CLAUDE_HARD_RSS_GB` | 15 | Hard kill threshold per process (GB) |
| `CLAUDE_MAX_HEADLESS_HOURS` | 4 | Max age for headless processes (hours) |
| `CLAUDE_MAX_PROCESSES` | 15 | Alert when total count exceeds this |
| `CLAUDE_SCAN_INTERVAL` | 300 | Seconds between scans in watch mode |

## Examples

```bash
# Quick check
/monitor-claude status

# Full scan with findings
/monitor-claude scan

# Auto-kill leakers and zombies
/monitor-claude scan --kill

# Continuous daemon mode (for scheduler)
/monitor-claude watch
```

## Scheduler Integration

Register with `/scheduler` for nightly runs:
```bash
/scheduler register monitor-claude --cron "*/30 * * * *" --cmd "scan --kill"
```
