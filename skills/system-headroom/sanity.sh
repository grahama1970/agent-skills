#!/usr/bin/env bash
# Sanity check for system-headroom skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Sanity check for system-headroom ==="

# Check SKILL.md exists
if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    exit 1
fi
echo "PASS: SKILL.md exists"

# Check scripts/check.sh exists and is executable
if [[ ! -x "$SCRIPT_DIR/scripts/check.sh" ]]; then
    echo "FAIL: scripts/check.sh not found or not executable"
    exit 1
fi
echo "PASS: scripts/check.sh exists"

# Check required system tools
if ! command -v df >/dev/null 2>&1; then
    echo "WARN: df not found"
else
    echo "PASS: df found"
fi

if ! command -v free >/dev/null 2>&1; then
    echo "WARN: free not found (may not be available on macOS)"
else
    echo "PASS: free found"
fi

# Check check.sh help
if "$SCRIPT_DIR/scripts/check.sh" --help >/dev/null 2>&1; then
    echo "PASS: check.sh --help works"
else
    echo "WARN: check.sh --help check failed"
fi

echo "=== Sanity check complete ==="
