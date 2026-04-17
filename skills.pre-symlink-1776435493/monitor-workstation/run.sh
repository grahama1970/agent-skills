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
monitor-workstation: Nightly workstation health monitor

Commands:
  check [--autofix] [--json] [--report]   Run all 8 health probes
  dashboard                                Rich TUI dashboard of latest report
  fix <probe-name>                         Manual auto-fix for a specific probe
  register-nightly                         Register 4am nightly job with scheduler
  help                                     Show this message

Examples:
  ./run.sh check
  ./run.sh check --autofix --json
  ./run.sh check --report
  ./run.sh fix cache-bloat
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
            --name "monitor-workstation-nightly" \
            --cron "0 4 * * *" \
            --command "$SCRIPT_DIR/run.sh check --autofix --json" \
            --description "Nightly workstation health: NVMe artifacts, caches, drive health"
        echo "Registered nightly job at 4am"
        ;;
    help|-h|--help)
        usage
        exit 0
        ;;
    *)
        exec uv run --directory "$SCRIPT_DIR" python monitor.py "$@"
        ;;
esac
