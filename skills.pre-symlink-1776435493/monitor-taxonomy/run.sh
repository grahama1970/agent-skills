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
monitor-taxonomy: Three-tier cascade taxonomy quality monitor

Commands:
  check [--tier N] [--probe NAME] [--autofix] [--json]   Run quality probes
  dashboard                                                Rich TUI dashboard
  status                                                   Show cascade status
  fix <probe-name>                                        Manual auto-fix
  register-nightly                                        Register with scheduler
  help                                                    Show this message

Tiers:
  0    All tiers (default)
  1    Heuristic Quality (P01-P05, auto-fix safe)
  15   Classifier/GPT Quality (P10-P12, after training)
  2    Brandon Teacher + Training (P20-P23)

Examples:
  ./run.sh check --tier 0 --autofix --json
  ./run.sh check --probe null-bridge-gc --json
  ./run.sh dashboard
  ./run.sh status
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
            --name "monitor-taxonomy-t1" --cron "0 3 * * *" \
            --command "$SCRIPT_DIR/run.sh check --tier 1 --autofix --json > ~/.pi/monitor-taxonomy/report_t1.json"
        "$SCHEDULER" register \
            --name "monitor-taxonomy-t15" --cron "15 3 * * *" \
            --command "$SCRIPT_DIR/run.sh check --tier 15 --json > ~/.pi/monitor-taxonomy/report_t15.json"
        "$SCHEDULER" register \
            --name "monitor-taxonomy-t2" --cron "30 3 * * *" \
            --command "$SCRIPT_DIR/run.sh check --tier 2 --json > ~/.pi/monitor-taxonomy/report_t2.json"
        echo "Registered 3 nightly jobs with scheduler"
        ;;
    help|-h|--help)
        usage
        exit 0
        ;;
    *)
        exec uv run --directory "$SCRIPT_DIR" python monitor.py "$@"
        ;;
esac
