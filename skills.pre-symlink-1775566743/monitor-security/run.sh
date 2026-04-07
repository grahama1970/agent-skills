#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load .env if present
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

usage() {
    cat <<EOF
monitor-security: Nightly self-hack orchestrator with four-tier probe cascade

Commands:
  check [--tier N] [--probe NAME] [--autofix] [--json]
                         Run security probes and report results
  dashboard              Show latest security report
  fix <probe-name>       Trigger auto-fix for a specific probe
  threat-intel [--dry-run]
                         Run hourly threat intelligence loop
  register-nightly       Register nightly self-hack jobs with scheduler
  register-hourly        Register hourly threat-intel jobs with scheduler
  help                   Show this message

Examples:
  ./run.sh check --tier 0 --autofix
  ./run.sh check --tier 1 --json
  ./run.sh check --tier 2 --dry-run
  ./run.sh threat-intel --dry-run
  ./run.sh dashboard
  ./run.sh register-nightly
  ./run.sh register-hourly
EOF
}

case "${1:-help}" in
    register-nightly)
        SCHEDULER="$PROJECT_ROOT/skills/scheduler/run.sh"
        if [[ ! -x "$SCHEDULER" ]]; then
            echo "ERROR: scheduler skill not found at $SCHEDULER" >&2
            exit 1
        fi

        # T0: Deterministic scans + auto-fix at 01:00
        "$SCHEDULER" register \
            --name "security-t0-nightly" --cron "0 1 * * *" \
            --command "$SCRIPT_DIR/run.sh check --tier 0 --autofix --json"

        # T1: OWASP analysis at 01:15
        "$SCHEDULER" register \
            --name "security-t1-nightly" --cron "15 1 * * *" \
            --command "$SCRIPT_DIR/run.sh check --tier 1 --json"

        # T2: Docker self-hack at 01:30
        "$SCHEDULER" register \
            --name "security-t2-nightly" --cron "30 1 * * *" \
            --command "$SCRIPT_DIR/run.sh check --tier 2 --json"

        # T3: Cascade validation at 02:00
        "$SCHEDULER" register \
            --name "security-t3-nightly" --cron "0 2 * * *" \
            --command "$SCRIPT_DIR/run.sh check --tier 3 --json"

        echo "Registered 4 nightly security jobs"
        ;;

    register-hourly)
        SCHEDULER="$PROJECT_ROOT/skills/scheduler/run.sh"
        if [[ ! -x "$SCHEDULER" ]]; then
            echo "ERROR: scheduler skill not found at $SCHEDULER" >&2
            exit 1
        fi

        # Hourly threat intel loop at :00
        "$SCHEDULER" register \
            --name "security-threat-intel-hourly" --cron "0 * * * *" \
            --command "$SCRIPT_DIR/run.sh threat-intel"

        echo "Registered hourly threat intelligence job"
        ;;

    help|-h|--help)
        usage
        exit 0
        ;;

    *)
        # Dispatch to Python CLI via uv
        exec uv run --directory "$SCRIPT_DIR" python monitor.py "$@"
        ;;
esac
