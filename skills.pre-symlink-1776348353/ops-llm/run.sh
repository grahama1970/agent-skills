#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
cd "$(dirname "$0")"

# ops-llm skill dispatcher
# Usage: run.sh <command> [args...]
# Commands: health, cache-clean, model-*, service-*, perf-monitor

cmd="${1:-help}"
shift || true

case "$cmd" in
    health)
        exec bash scripts/health.sh "$@"
        ;;
    cache-clean)
        exec bash scripts/cache-clean.sh "$@"
        ;;
    model-list)
        exec bash scripts/model-list.sh "$@"
        ;;
    model-pull)
        exec bash scripts/model-pull.sh "$@"
        ;;
    model-remove|model-rm)
        exec bash scripts/model-remove.sh "$@"
        ;;
    model-show)
        exec bash scripts/model-show.sh "$@"
        ;;
    service-status)
        exec bash scripts/service-status.sh "$@"
        ;;
    service-control)
        exec bash scripts/service-control.sh "$@"
        ;;
    service-logs)
        exec bash scripts/service-logs.sh "$@"
        ;;
    perf-monitor|monitor)
        exec bash scripts/perf-monitor.sh "$@"
        ;;
    help|--help|-h)
        echo "Usage: run.sh <command> [args...]"
        echo ""
        echo "Commands:"
        echo "  health            - Check LLM endpoint health"
        echo "  cache-clean       - Clean model caches"
        echo ""
        echo "Model Management (Docker-based Ollama):"
        echo "  model-list        - List installed models"
        echo "  model-pull        - Pull a model from registry"
        echo "  model-remove      - Remove a model"
        echo "  model-show        - Show model details"
        echo ""
        echo "Service Management (Docker container):"
        echo "  service-status    - Check container status"
        echo "  service-control   - Start/stop/restart container"
        echo "  service-logs      - View container logs"
        echo ""
        echo "Performance:"
        echo "  perf-monitor      - Monitor GPU, models, container stats"
        exit 0
        ;;
    *)
        echo "Unknown command: $cmd" >&2
        echo "Run 'run.sh help' for usage" >&2
        exit 1
        ;;
esac
