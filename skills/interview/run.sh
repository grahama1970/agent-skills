#!/usr/bin/env bash
# Interview Skill - Structured human-agent Q&A
#
# Usage:
#   ./run.sh --file questions.json              # Auto-detect mode
#   ./run.sh --file questions.json --mode tui   # Force TUI
#   ./run.sh --file questions.json --mode html  # Force HTML
#   ./run.sh --resume                           # Resume latest session
#   echo '{"questions":[...]}' | ./run.sh       # Pipe JSON in

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_ROOT="${PI_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"

# Load environment
[[ -f "$PI_ROOT/.env" ]] && { set -a; source "$PI_ROOT/.env"; set +a; }

# Dependencies for uvx
DEPS="textual rich"

# Check if we need TUI mode
needs_tui() {
    for arg in "$@"; do
        [[ "$arg" == "--mode" ]] && return 0
        [[ "$arg" == "tui" ]] && return 0
    done
    # Auto mode might need TUI if no display
    [[ -z "$DISPLAY" ]] && [[ -z "$WAYLAND_DISPLAY" ]] && return 0
    return 1
}

# Find Python - prefer venv, fall back to uvx for TUI deps
find_python() {
    # Try project venv first
    if [[ -n "$PI_VENV" ]] && [[ -f "$PI_VENV/bin/python" ]]; then
        if "$PI_VENV/bin/python" -c "import textual" 2>/dev/null; then
            echo "$PI_VENV/bin/python"
            return 0
        fi
    fi

    if [[ -f "$PI_ROOT/.venv/bin/python" ]]; then
        if "$PI_ROOT/.venv/bin/python" -c "import textual" 2>/dev/null; then
            echo "$PI_ROOT/.venv/bin/python"
            return 0
        fi
    fi

    # Check system python
    if python3 -c "import textual" 2>/dev/null; then
        echo "python3"
        return 0
    fi

    # No textual available
    return 1
}

# Handle piped input
TEMP_FILE=""
if [[ ! -t 0 ]]; then
    TEMP_FILE=$(mktemp)
    cat > "$TEMP_FILE"
    set -- --file "$TEMP_FILE" "$@"
fi

# Cleanup on exit
cleanup() {
    [[ -n "$TEMP_FILE" ]] && [[ -f "$TEMP_FILE" ]] && rm -f "$TEMP_FILE"
}
trap cleanup EXIT

# Set pythonpath
export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

# Try to find Python with textual
if PYTHON=$(find_python); then
    exec "$PYTHON" -m interview "$@"
else
    # Use uvx to run with dependencies
    echo "Using uvx to load dependencies: $DEPS" >&2
    exec uvx --with textual --with rich python -m interview "$@"
fi
