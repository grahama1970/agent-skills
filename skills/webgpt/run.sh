#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/webgpt_cli.py" "$@"
