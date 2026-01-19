#!/usr/bin/env bash
#
# Embedding Skill - Launcher
#
# Usage:
#   ./run.sh serve              Start FastAPI server (runs forever)
#   ./run.sh embed --text "q"   Embed text
#   ./run.sh info               Show configuration
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Use uv run to automatically install deps from pyproject.toml
exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/embed.py" "$@"
