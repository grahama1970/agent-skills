#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/ops-excalidraw/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"
uv run --project . python scripts/ops_excalidraw.py "$@"
