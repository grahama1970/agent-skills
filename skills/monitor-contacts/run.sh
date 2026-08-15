#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'


PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

cd "$SCRIPT_DIR"

# Ensure venv
if [[ ! -d .venv ]]; then
    uv venv .venv
    uv pip install -r pyproject.toml --python .venv/bin/python 2>/dev/null || true
fi

CMD="${1:-help}"
shift || true

case "$CMD" in
    monitor)
        .venv/bin/python -m monitor_contacts monitor "$@"
        ;;
    start)
        .venv/bin/python -m monitor_contacts start "$@"
        ;;
    stop)
        .venv/bin/python -m monitor_contacts stop "$@"
        ;;
    status)
        .venv/bin/python -m monitor_contacts status "$@"
        ;;
    cycle)
        .venv/bin/python -m monitor_contacts cycle "$@"
        ;;
    report)
        .venv/bin/python -m monitor_contacts report "$@"
        ;;
    changes)
        .venv/bin/python -m monitor_contacts changes "$@"
        ;;
    relationship-graph)
        .venv/bin/python -m monitor_contacts relationship-graph "$@"
        ;;
    config)
        .venv/bin/python -m monitor_contacts config "$@"
        ;;
    help|--help|-h)
        echo "monitor-contacts — Always-on contact freshness monitoring"
        echo ""
        echo "Commands:"
        echo "  monitor            Start monitoring (foreground)"
        echo "  start              Start as background service"
        echo "  stop               Stop background service"
        echo "  status             Check service status"
        echo "  cycle              Run one monitoring cycle manually"
        echo "  report             Show contact freshness report"
        echo "  changes [--since]  Show recent changes"
        echo "  relationship-graph --input contacts.json  Export local reconnect graph records"
        echo "  config [--key val] Configure monitoring"
        echo ""
        echo "Options:"
        echo "  --interval weekly     Schedule interval (daily/weekly/monthly)"
        echo "  --budget N            Max /dogpile calls per cycle (default: 10)"
        echo "  --alert-channel NAME  Discord channel for alerts"
        ;;
    *)
        echo "Unknown command: $CMD (try: monitor, start, stop, status, cycle, report, changes, relationship-graph)"
        exit 1
        ;;
esac
