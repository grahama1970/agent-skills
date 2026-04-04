---
name: monitor-ollama
description: >
  Continuous Ollama health monitor with auto-restart. Detects hung runner
  processes (1000%+ CPU spin where /api/tags responds but /api/chat hangs).
  Runs the watchdog check and restarts Ollama if needed. Designed to run
  on a scheduler every 2 minutes.
triggers:
  - monitor ollama
  - is ollama hung
  - ollama watchdog
  - check ollama health
  - ollama runner stuck
allowed-tools:
  - Bash
  - Read
metadata:
  short-description: Continuous Ollama watchdog with auto-restart on hung runner
provides:
  - ollama-monitoring
composes:
  - ops-llm
  - task-monitor

taxonomy:
  - monitoring
  - operations
  - llm
---

# monitor-ollama

Continuous health monitor for Ollama. Catches the specific failure mode where
the Ollama runner process hangs at 1000%+ CPU, causing all chat requests to
timeout while the API tags endpoint still responds.

## Quick Start

```bash
# One-shot health check
./scripts/check.sh

# Install cron watchdog (every 2 minutes)
./scripts/install-cron.sh

# Remove cron watchdog
./scripts/uninstall-cron.sh
```

## What It Checks

1. **Process alive**: Is the `ollama` process running?
2. **API reachable**: Does `/api/tags` respond within 5s?
3. **Model responsive**: Does `/api/chat` complete within 8s? (catches hung runner)

## Auto-Restart Behavior

When the chat probe times out:
1. Tries `systemctl restart ollama`
2. Falls back to `pkill -9 ollama` + start
3. Verifies recovery
4. Logs to `/tmp/ollama_watchdog.log`

## Environment Variables

| Variable                 | Default                    | Description               |
| ------------------------ | -------------------------- | ------------------------- |
| `OLLAMA_API_BASE`        | `http://127.0.0.1:11434`  | Ollama HTTP endpoint      |
| `OLLAMA_MODEL`           | `qwen2.5:0.5b`            | Model to probe            |
| `OLLAMA_WATCHDOG_TIMEOUT`| `8`                        | Chat probe timeout (sec)  |
| `WATCHDOG_DRY_RUN`       | `0`                        | Set to 1 for check-only   |
