---
name: monitor-pi
description: >
  Continuous Pi agent infrastructure health monitor. Checks the D-Bus daemon
  (embry-agent.service), scheduler daemon, scillm service, and scheduler job
  success rates. Detects crash-looping, stale jobs, and log bloat.
  Fires Discord alerts on failures. Designed to run on a scheduler.
triggers:
  - monitor pi health
  - check pi daemon status
  - is the pi daemon running
  - pi infrastructure health
  - check embry agent service
  - scheduler health check
  - are scheduler jobs failing
  - pi service status
allowed-tools:
  - Bash
  - Read
metadata:
  short-description: Pi agent infrastructure health watchdog
provides:
  - pi-daemon-monitoring
  - scheduler-health-monitoring
  - dbus-health-monitoring
composes:
  - ops-embry-agent
  - scheduler
  - memory
  - agentic-evals
taxonomy:
  - monitoring
  - operations
disciplines:
  - observability-operations
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# monitor-pi

Continuous health watchdog for Pi agent infrastructure. Monitors:

- **D-Bus daemon** (`embry-agent.service`): Running, crash-looping, D-Bus name registered
- **Scheduler daemon**: Running, job success/failure rates, log bloat
- **scillm service** (`embry-scillm.service`): Running status
- **Scheduler job audit**: Detects jobs with stale paths or disabled state

## Usage

```bash
# One-shot health check (for scheduler or manual)
./run.sh check

# Continuous monitoring (runs every 5 minutes)
./run.sh watch

# JSON output for dashboards
./run.sh check --json
```

## Scheduler Registration

```bash
# Register as a scheduler job (every 30 minutes)
cd .pi/skills/scheduler && uv run python scheduler.py register \
  --name monitor-pi \
  --command "$HOME/.pi/skills/monitor-pi/run.sh check" \
  --cron "*/30 * * * *"
```
