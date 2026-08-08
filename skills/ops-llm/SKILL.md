---
name: ops-llm
description: >
  Local LLM operations: health checks, cache management, Ollama model management,
  Docker service control, and performance monitoring.
  Probe Ollama/vLLM/SGLang endpoints, manage Docker-based Ollama models,
  monitor GPU usage and running models.
triggers:
  - check llm
  - is ollama running
  - llm health
  - vllm status
  - clean llm cache
  - free gpu memory
  - clear huggingface cache
  - ollama status
  - list ollama models
  - pull ollama model
  - remove ollama model
  - show model details
  - restart ollama
  - check gpu usage
  - monitor llm performance
allowed-tools: Bash
metadata:
  short-description: Local LLM health, cache, Docker-based Ollama model/service management

provides:
  - ops-llm
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - observability-operations
  - model-ops
---

# LLM Ops

Manage local LLM runtimes, caches, Docker-based Ollama models, and performance monitoring.

## Commands

```bash
# Check all common LLM endpoints (Ollama, vLLM, SGLang)
./scripts/health.sh

# Check specific endpoint
./scripts/health.sh --target ollama:http://127.0.0.1:11434

# Continue even if some fail
./scripts/health.sh --warn-only

# Show cache sizes (dry-run)
./scripts/cache-clean.sh

# Actually clean caches
./scripts/cache-clean.sh --execute

# Clean additional path
./scripts/cache-clean.sh --path ~/.cache/torch --execute

# Model Management (Docker-based Ollama)
# List installed models
./scripts/model-list.sh
./scripts/model-list.sh --format json

# Pull a model from registry
./scripts/model-pull.sh llama3.2:1b
./scripts/model-pull.sh mistral:7b --dry-run

# Remove a model
./scripts/model-remove.sh old-model:tag
./scripts/model-remove.sh unused-model --dry-run

# Show model details
./scripts/model-show.sh qwen3:1.7b
./scripts/model-show.sh llama3.2:1b --format json

# Service Management (Docker container)
# Check container status
./scripts/service-status.sh
./scripts/service-status.sh --format json

# Control container (start/stop/restart)
./scripts/service-control.sh --action status
./scripts/service-control.sh --action restart --dry-run

# View container logs
./scripts/service-logs.sh --lines 20
./scripts/service-logs.sh --follow

# Performance Monitoring
# Monitor GPU, models, and container stats
./scripts/perf-monitor.sh
./scripts/perf-monitor.sh --format json
```

## Watchdog (auto-restart hung Ollama)

```bash
# One-shot check — restarts Ollama if runner is hung
./scripts/watchdog.sh

# Dry-run (check only, no restart)
WATCHDOG_DRY_RUN=1 ./scripts/watchdog.sh

# Install as cron (every 2 minutes)
(crontab -l 2>/dev/null; echo "*/2 * * * * $(pwd)/scripts/watchdog.sh >> /tmp/ollama_watchdog.log 2>&1") | crontab -
```

The watchdog detects the specific failure mode where the Ollama runner process
hangs (1000%+ CPU spin) and all chat requests timeout, while `/api/tags` still
responds. It probes `/api/chat` with a timeout and restarts Ollama if hung.

## Default Endpoints Checked

- Ollama: `http://127.0.0.1:11434`
- vLLM: `http://127.0.0.1:8000`
- SGLang: `http://127.0.0.1:30000`

## Default Cache Directories

- `~/.cache/ollama`
- `~/.cache/huggingface`
- `~/.cache/vllm`

## Docker-based Ollama

All Ollama model and service management commands interact with Ollama running in a Docker container:

- **Container name**: `scillm-ollama`
- **Port**: `11434` (HTTP API)
- **Image**: `ollama/ollama:0.14.3-rc2`

Commands use `docker exec scillm-ollama ollama <command>` pattern or HTTP API `http://localhost:11434/api/...`

## Environment Variables

| Variable             | Default     | Description                  |
| -------------------- | ----------- | ---------------------------- |
| `LLM_HEALTH_TIMEOUT` | 2           | Seconds to wait per endpoint |
| `LLM_CACHE_DIRS`     | (see above) | Space-separated cache paths  |
