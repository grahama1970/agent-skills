#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
uv run --project "$SCRIPT_DIR" python -m py_compile "$SCRIPT_DIR"/scripts/*.py
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/cli.py" verify
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/cli.py" --help >/dev/null
