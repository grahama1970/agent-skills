#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Use uv run with project environment
exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/arxiv_learn.py" "$@"
