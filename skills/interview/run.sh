#!/bin/bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run with uv for dependency management
# Add parent directory to PYTHONPATH so python -m interview works
PARENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
exec uv run --project "${SCRIPT_DIR}" env PYTHONPATH="${PARENT_DIR}" python -m interview "$@"
