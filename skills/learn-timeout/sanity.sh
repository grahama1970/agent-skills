#!/usr/bin/env bash
# Sanity check for learn-timeout
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== learn-timeout sanity check ==="

# 1. Check run.sh exists and is executable
echo "1/5 Checking run.sh..."
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh not found or not executable"
    exit 1
fi

# 2. Check help output
echo "2/5 Checking help output..."
"$SCRIPT_DIR/run.sh" help > /dev/null || { echo "FAIL: help command failed"; exit 1; }

# 3. Check required scripts exist
echo "3/5 Checking scripts directory..."
for script in collect.py train.py predict.py observe.py status.py; do
    if [[ ! -f "$SCRIPT_DIR/scripts/$script" ]]; then
        echo "FAIL: scripts/$script not found"
        exit 1
    fi
done

# 4. Check symlinked data/models directories
echo "4/5 Checking data and models symlinks..."
if [[ ! -L "$SCRIPT_DIR/data" ]]; then
    echo "WARNING: data/ is not a symlink (expected link to 12TB)"
fi
if [[ ! -L "$SCRIPT_DIR/models" ]]; then
    echo "WARNING: models/ is not a symlink (expected link to 12TB)"
fi

# 5. Test status command (non-destructive)
echo "5/5 Testing status command..."
"$SCRIPT_DIR/run.sh" status > /dev/null 2>&1 || { echo "WARNING: status command failed (may need training data)"; }

echo "learn-timeout sanity check PASSED"
