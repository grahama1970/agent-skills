#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SKILL_DIR"

if [ ! -d ".venv" ]; then
    uv venv .venv --quiet
    uv pip install --quiet -e .
fi

source .venv/bin/activate
exec python -m agents_registry.cli "$@"
