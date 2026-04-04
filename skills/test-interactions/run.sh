#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SKILL_DIR"
unset VIRTUAL_ENV
exec uv run python test_interactions.py "$@"
