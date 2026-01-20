#!/bin/bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run with uv for dependency management
# TUI mode requires stdout/in, uv run handles this fine
exec uv run --project "${SCRIPT_DIR}" python -m interview "$@"
