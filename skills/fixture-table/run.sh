#!/usr/bin/env bash
# Wrapper script for fixture-table skill
# Usage: ./run.sh [generate options]

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Run via uv with inline script metadata
exec uv run generate.py "$@"
