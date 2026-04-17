#!/usr/bin/env bash
# Evidence Case Viewer — launch the KDE/QML app
#
# Usage:
#   ./run.sh                              # Open viewer (tail mode)
#   ./run.sh --question "How does..."     # Open viewer + run pipeline
#   ./run.sh --emit-only "How does..."    # Headless: NDJSON to stdout
#   ./run.sh -q "How does..."             # Short form
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# System python3 has PySide6. Add memory venv site-packages for graph_memory.
MEMORY_SITE="/home/graham/workspace/experiments/memory/.venv/lib/python3.12/site-packages"
export PYTHONPATH="${MEMORY_SITE}:${PYTHONPATH:-}"

exec python3 "$SCRIPT_DIR/app.py" "$@"
