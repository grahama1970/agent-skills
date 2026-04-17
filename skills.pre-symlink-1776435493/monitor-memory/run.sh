#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Load .env if present
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

usage() {
    cat <<EOF
monitor-memory: Nightly memory & system health orchestrator

Commands:
  check [--tier N] [--probe NAME] [--autofix] [--json]   Run health probes
  dashboard                                                Rich TUI dashboard
  fix <probe-name>                                        Manual auto-fix
  register-nightly                                        Register with scheduler
  help                                                    Show this message

Tiers:
  1  Memory & Data Health (auto-fix safe)
  2  Persona Lifecycle (report only)
  3  Integration Smoke Tests (detect + dispatch)
  4  Project Health (heavyweight)
  5  Infrastructure (lightweight)
  6  Model Health (registry, shadow, training data)
  7  Pytest Suite (339+ tests: health, unit, performance)

Examples:
  ./run.sh check --tier 1 --autofix --json
  ./run.sh check --probe embedding-coverage --json
  ./run.sh dashboard
  ./run.sh register-nightly
EOF
}

case "${1:-help}" in
    register-nightly)
        SCHEDULER="$PROJECT_ROOT/.pi/skills/scheduler/run.sh"
        if [[ ! -x "$SCHEDULER" ]]; then
            echo "ERROR: scheduler skill not found at $SCHEDULER" >&2
            exit 1
        fi

        "$SCHEDULER" register \
            --name "monitor-memory-t1" --cron "0 5 * * *" \
            --command "$SCRIPT_DIR/run.sh check --tier 1 --autofix --json > ~/.pi/monitor-memory/report_t1.json"
        "$SCHEDULER" register \
            --name "monitor-memory-t2" --cron "15 5 * * *" \
            --command "$SCRIPT_DIR/run.sh check --tier 2 --json > ~/.pi/monitor-memory/report_t2.json"
        "$SCHEDULER" register \
            --name "monitor-memory-t3" --cron "30 5 * * *" \
            --command "$SCRIPT_DIR/run.sh check --tier 3 --json > ~/.pi/monitor-memory/report_t3.json"
        "$SCHEDULER" register \
            --name "monitor-memory-t4" --cron "0 6 * * *" \
            --command "$SCRIPT_DIR/run.sh check --tier 4 --json > ~/.pi/monitor-memory/report_t4.json"
        "$SCHEDULER" register \
            --name "monitor-memory-t5" --cron "45 5 * * *" \
            --command "$SCRIPT_DIR/run.sh check --tier 5 --json > ~/.pi/monitor-memory/report_t5.json"
        "$SCHEDULER" register \
            --name "monitor-memory-t6" --cron "15 6 * * *" \
            --command "$SCRIPT_DIR/run.sh check --tier 6 --json > ~/.pi/monitor-memory/report_t6.json"

        # Tier 7: Pytest suite (runs after all other tiers complete)
        "$SCHEDULER" register \
            --name "monitor-memory-t7" --cron "30 6 * * *" \
            --command "$SCRIPT_DIR/run.sh check --tier 7 --json > ~/.pi/monitor-memory/report_t7.json"

        # Best-practices docs ingestion updates (run before T1 so docs are fresh)
        BEST_PRACTICES_DIR="$PROJECT_ROOT/.pi/skills"
        "$SCHEDULER" register \
            --name "docs-update-arangodb" --cron "45 4 * * *" \
            --command "$BEST_PRACTICES_DIR/best-practices-arangodb/run.sh update 2>&1 | head -20"
        echo "Registered 7 nightly jobs + 1 docs-update job with scheduler"
        ;;
    help|-h|--help)
        usage
        exit 0
        ;;
    *)
        exec uv run --directory "$SCRIPT_DIR" python monitor.py "$@"
        ;;
esac
