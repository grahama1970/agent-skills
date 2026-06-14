#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/book-extraction-verifier/.venv}"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"

"$SCRIPT_DIR/run.sh" doctor >/tmp/book-extraction-verifier-doctor.json
PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}" uv run --project "$SCRIPT_DIR" pytest -p no:cacheprovider "$SCRIPT_DIR/tests" -q
rm -rf "$SCRIPT_DIR/.pytest_cache" "$SCRIPT_DIR/book_extraction_verifier/__pycache__" "$SCRIPT_DIR/tests/__pycache__"
