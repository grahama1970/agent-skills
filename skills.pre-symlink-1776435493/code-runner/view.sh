#!/usr/bin/env bash
# /code-runner viewers — web dashboards for run inspection
# Phase 2-3 of multica-inspired upgrades
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-help}" in
    run)
        # View a single run in browser
        shift
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/run_viewer.py" serve "$@"
        ;;
    latest)
        # View the most recent run in browser
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/run_viewer.py" serve --latest
        ;;
    fleet)
        # Fleet dashboard - monitor multiple runs
        shift
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/fleet_dashboard.py" serve "$@"
        ;;
    list)
        # List all discovered runs (CLI output)
        shift
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/fleet_dashboard.py" list-runs "$@"
        ;;
    report)
        # Generate static HTML report for a run
        shift
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/run_viewer.py" generate "$@"
        ;;
    help|--help|-h|"")
        echo "Usage: ./view.sh {run|latest|fleet|list|report|help}"
        echo ""
        echo "Commands:"
        echo "  run <output_dir>      View single run in browser (port 8765)"
        echo "  latest                View most recent run in browser"
        echo "  fleet                 Fleet dashboard - all runs (port 8766)"
        echo "  list [--json]         List all discovered runs"
        echo "  report <dir> [-o f]   Generate static HTML report"
        echo ""
        echo "Examples:"
        echo "  ./view.sh latest                    # Open latest run"
        echo "  ./view.sh fleet                     # Fleet dashboard"
        echo "  ./view.sh run /tmp/code-runner/t1   # View specific run"
        echo "  ./view.sh list --json               # JSON output for scripts"
        ;;
    *)
        echo "Unknown command: $1" >&2
        exit 1
        ;;
esac
