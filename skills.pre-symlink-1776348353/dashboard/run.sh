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

# Check for uv or use python3
if command -v uv &> /dev/null; then
    EXEC=(uv run --project "$SCRIPT_DIR" python)
else
    EXEC=(python3)
fi

case "${1:-tui}" in
    tui)
        "${EXEC[@]}" "$SCRIPT_DIR/dashboard.py" tui
        ;;
    json)
        "${EXEC[@]}" "$SCRIPT_DIR/dashboard.py" json
        ;;
    text)
        "${EXEC[@]}" "$SCRIPT_DIR/dashboard.py" text
        ;;
    monitor)
        shift
        "${EXEC[@]}" "$SCRIPT_DIR/dashboard.py" monitor "$@"
        ;;
    --help|-h)
        echo "Usage: ./run.sh [tui|json|text|monitor]"
        echo ""
        echo "Commands:"
        echo "  tui       Live Rich TUI dashboard (default)"
        echo "  json      JSON output (pipeable to /create-figure)"
        echo "  text      Plain text summary"
        echo "  monitor   Aggregated monitor-* skill reports [--json]"
        ;;
    *)
        echo "Unknown command: $1"
        echo "Usage: ./run.sh [tui|json|text|monitor]"
        exit 1
        ;;
esac
