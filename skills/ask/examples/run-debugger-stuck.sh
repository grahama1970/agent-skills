#!/usr/bin/env bash
# Example: /debugger capture on sample_target before patching.
set -euo pipefail
ASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ASK_DIR/examples"
SAMPLE="$ASK_DIR/examples/sample_target.py"
PROOF="$ASK_DIR/examples/debugger-proof.json"
DEBUGGER_RUN="$(dirname "$ASK_DIR")/debugger/run.sh"
if [[ ! -x "$DEBUGGER_RUN" ]]; then
  echo "debugger run.sh not found at $DEBUGGER_RUN" >&2
  exit 1
fi
PYTHON="${PYTHON:-}"
if [[ -x "$ASK_DIR/.venv/bin/python" ]]; then
  PYTHON="$ASK_DIR/.venv/bin/python"
else
  PYTHON="$(command -v python3)"
fi
exec "$DEBUGGER_RUN" \
  --break "${SAMPLE}:7" \
  --local raw \
  --local candidate \
  --out "$PROOF" \
  -- \
  "$PYTHON" debug_repro.py
