#!/usr/bin/env bash
# Extractor skill - Preset-First Agentic Document Extraction
#
# Usage:
#   ./run.sh document.pdf                    # Auto mode (recommended)
#   ./run.sh document.pdf --fast             # Quick extraction, no LLM
#   ./run.sh document.pdf --accurate         # Full LLM enhancement
#   ./run.sh document.pdf --offline          # Deterministic, no network
#   ./run.sh document.pdf --markdown         # Output markdown to stdout
#   ./run.sh document.pdf --out ./results    # Custom output directory
#   ./run.sh document.pdf --preset arxiv     # Force preset
#   ./run.sh ./documents/                    # Batch mode (directory)
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Try to detect extractor project relative to this skill (sibling in workspace)
DEFAULT_ROOT="$(cd "$SCRIPT_DIR/../../../../extractor" >/dev/null 2>&1 && pwd)"
EXTRACTOR_ROOT="${EXTRACTOR_ROOT:-${DEFAULT_ROOT:-/home/graham/workspace/experiments/extractor}}"

# Load environment if available
[[ -f "$EXTRACTOR_ROOT/.env" ]] && { set -a; source "$EXTRACTOR_ROOT/.env"; set +a; }

# Use extractor's virtual environment
PYTHON="${EXTRACTOR_ROOT}/.venv/bin/python"

if [[ ! -f "$PYTHON" ]]; then
    echo "Error: Extractor venv not found at $EXTRACTOR_ROOT/.venv" >&2
    echo "Install extractor first:" >&2
    echo "  cd $EXTRACTOR_ROOT && uv venv && uv pip install -e ." >&2
    exit 1
fi

# Pass all arguments to extract.py
exec "$PYTHON" "$SCRIPT_DIR/extract.py" "$@"
