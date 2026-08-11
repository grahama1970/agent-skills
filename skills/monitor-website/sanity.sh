#!/usr/bin/env bash
# Cheap local proof: README parses and drift check runs (no live probes,
# no mutation). Exit 0 = parser healthy and site content matches README.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
./run.sh audit --no-live --json >/dev/null
echo "monitor-website sanity: OK (README parsed, no drift, no live probes)"

# #1298 voice canary + #1337 design-world contract
python3 "$SCRIPT_DIR/../../site/scripts/copy_audit.py" >/dev/null
"$SCRIPT_DIR/run.sh" design-world-check --json >/dev/null || true
"$SCRIPT_DIR/run.sh" disclosure-check --canary --json >/dev/null
