#!/usr/bin/env bash
#
# Embedding Skill - Launcher
#
# Usage:
#   ./run.sh serve         Start FastAPI server
#   ./run.sh embed --text "query"  Embed text
#   ./run.sh info          Show configuration
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Use uvx for isolated environment with heavy deps
exec uvx --from "${SCRIPT_DIR}" python "${SCRIPT_DIR}/embed.py" "$@"
