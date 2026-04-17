#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Entry point for /analyze-elf skill.
# Commands: analyze, headers, symbols, strings, bundled-source, figure, walkthrough
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Check that binutils is available
for tool in readelf nm strings; do
    if ! command -v "$tool" &>/dev/null; then
        echo "ERROR: '$tool' not found. Install binutils:"
        echo "  sudo apt install binutils"
        exit 1
    fi
done

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/analyze_elf.py" "$@"
