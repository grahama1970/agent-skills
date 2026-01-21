#!/usr/bin/env bash
# Sanity check for arango-ops skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[sanity] Testing arango-ops..."

# Check run.sh exists and is executable
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh not executable" >&2
    exit 1
fi

# Check help works
if ! "$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1; then
    echo "FAIL: run.sh --help failed" >&2
    exit 1
fi

# Check dump.sh exists
if [[ ! -f "$SCRIPT_DIR/scripts/dump.sh" ]]; then
    echo "FAIL: scripts/dump.sh missing" >&2
    exit 1
fi

# Check maintain.py exists
if [[ ! -f "$SCRIPT_DIR/scripts/maintain.py" ]]; then
    echo "FAIL: scripts/maintain.py missing" >&2
    exit 1
fi

# Check python-arango is importable
if ! python3 -c "from arango import ArangoClient" 2>/dev/null; then
    echo "WARN: python-arango not installed (pip install python-arango)"
fi

echo "[sanity] arango-ops OK"
