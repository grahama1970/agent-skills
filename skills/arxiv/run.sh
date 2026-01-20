#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run with uv for dependency management
# Arxiv needs scillm, rich, requests
exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/arxiv_cli.py" "$@"
