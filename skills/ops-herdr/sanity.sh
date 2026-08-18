#!/usr/bin/env bash
# Behavioral gates:
# - static: modules compile and the CLI self-check passes
# - contract: a malformed Herdr reply fails closed (exercised by `verify`)
# - live: when Herdr is reachable, build a real workspace/tab/split topology,
#   move a live pane across workspaces, and read every id back before cleanup
# The live gate exists because compiling modules and checking --help is exactly
# what let the pre-0.8 agent argv rot undetected.
unset VIRTUAL_ENV
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

uv run --project "$SCRIPT_DIR" python -m py_compile "$SCRIPT_DIR"/scripts/*.py "$SCRIPT_DIR"/evals/*.py
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/cli.py" verify
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/cli.py" --help >/dev/null

HERDR_BIN="${HERDR_BIN:-herdr}"
if ! command -v "$HERDR_BIN" >/dev/null 2>&1 || ! "$HERDR_BIN" status >/dev/null 2>&1; then
    echo "SKIP: Herdr unreachable; live topology gate not run (static checks passed)"
    exit 0
fi

if [[ "${OPS_HERDR_SKIP_LIVE:-0}" == "1" ]]; then
    echo "SKIP: OPS_HERDR_SKIP_LIVE=1; live topology gate not run (static checks passed)"
    exit 0
fi

uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/evals/live_space_e2e.py" >/dev/null
echo "PASS: live Herdr topology, cross-workspace move, and cleanup verified"
