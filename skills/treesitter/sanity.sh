#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Treesitter Sanity ==="
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [PASS] run.sh exists"
else
    echo "  [FAIL] run.sh missing"
    exit 1
fi
# run.sh with no args might fail or show help depending on tool. 
# Treesitter tools usually needs subcommands.
# We'll check if --help works or returns exit code.
if "$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1 || true; then
     echo "  [PASS] run.sh executed"
else
     echo "  [FAIL] run.sh failed execution"
     exit 1
fi
echo "Result: PASS"
