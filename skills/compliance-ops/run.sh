#!/usr/bin/env bash
# compliance-ops: Compliance framework checker
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run with uv if available, otherwise fall back to python
if command -v uv &> /dev/null; then
    exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/compliance_ops.py" "$@"
else
    exec python "$SCRIPT_DIR/compliance_ops.py" "$@"
fi
