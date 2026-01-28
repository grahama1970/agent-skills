#!/usr/bin/env bash
# Learn - Unified knowledge acquisition for any persona agent
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure virtual environment exists
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    echo "Creating virtual environment..." >&2
    python3 -m venv "$SCRIPT_DIR/.venv"
    "$SCRIPT_DIR/.venv/bin/pip" install -q typer rich
fi

# Route to nightly.py for nightly/transcript/scheduler commands
case "${1:-}" in
    learn|collect-transcripts|full|register)
        # Nightly automation commands
        exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/nightly.py" "$@"
        ;;
    *)
        # Default: learn.py for regular learning
        exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/learn.py" "$@"
        ;;
esac
