#!/usr/bin/env bash
# Jev skill entrypoint. Usage: ./run.sh <command> [args...]
set -euo pipefail
cd "$(dirname "$0")"
exec uv run --quiet --with httpx,typer,loguru python scripts/jev.py "$@"
