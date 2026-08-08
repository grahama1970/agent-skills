#!/usr/bin/env bash
# Opt-in live E2E gate: runs the real nightly and asserts real-world outcomes.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/e2e_eval.py" "$@"
