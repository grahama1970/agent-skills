#!/usr/bin/env bash
#
# Distill Skill Runner
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Use uv run to execute in the project environment defined by pyproject.toml
# This ensures rich, tqdm, dotenv, etc. are available.
exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/distill.py" "$@"
