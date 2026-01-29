#!/usr/bin/env bash
# create-code: Horus coding orchestration pipeline
# 100% self-contained via uvx - no .venv needed
set -eo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

# Use uvx for self-contained execution with all dependencies
exec uvx --with typer \
         python3 orchestrator.py "$@"
