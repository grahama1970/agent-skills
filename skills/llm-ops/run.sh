#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# llm-ops skill dispatcher
# Usage: run.sh <command> [args...]
# Commands: health, cache-clean

cmd="${1:-help}"
shift || true

case "$cmd" in
    health)
        exec bash scripts/health.sh "$@"
        ;;
    cache-clean)
        exec bash scripts/cache-clean.sh "$@"
        ;;
    help|--help|-h)
        echo "Usage: run.sh <command> [args...]"
        echo ""
        echo "Commands:"
        echo "  health       - Check LLM endpoint health"
        echo "  cache-clean  - Clean model caches"
        exit 0
        ;;
    *)
        echo "Unknown command: $cmd" >&2
        echo "Run 'run.sh help' for usage" >&2
        exit 1
        ;;
esac
