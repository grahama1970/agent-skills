#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Route commands
case "${1:-help}" in
    experiment)
        shift
        uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/orchestrator.py" experiment "$@"
        ;;
    preflight)
        shift
        uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/orchestrator.py" preflight "$@"
        ;;
    single)
        shift
        uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/orchestrator.py" single "$@"
        ;;
    results)
        shift
        uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/orchestrator.py" results "$@"
        ;;
    harness)
        shift
        uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/harness.py" experiment "$@"
        ;;
    harness-logs)
        shift
        uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/harness.py" logs "$@"
        ;;
    harness-results)
        shift
        uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/harness.py" results "$@"
        ;;
    help|--help|-h)
        echo "Usage: ./run.sh {experiment|preflight|single|results|harness|harness-logs|harness-results}"
        echo ""
        echo "Commands:"
        echo "  experiment  Run 3 concurrent subagent classifier training loops"
        echo "  preflight   Verify dependencies and dataset before dispatching"
        echo "  single      Run one model locally (no subagent) for testing"
        echo "  results     Show results from the last experiment"
        ;;
    *)
        echo "Unknown command: $1"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
