#!/usr/bin/env bash
# Sanity check for ops-docker skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Sanity check for ops-docker ==="

# Check docker exists
if ! command -v docker >/dev/null 2>&1; then
    echo "WARN: docker not found (required for full functionality)"
else
    echo "PASS: docker found"
fi

# Check SKILL.md exists
if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    exit 1
fi
echo "PASS: SKILL.md exists"

# Check scripts exist
if [[ ! -x "$SCRIPT_DIR/scripts/prune.sh" ]]; then
    echo "FAIL: scripts/prune.sh not found or not executable"
    exit 1
fi
echo "PASS: scripts/prune.sh exists"

if [[ ! -x "$SCRIPT_DIR/scripts/redeploy.sh" ]]; then
    echo "FAIL: scripts/redeploy.sh not found or not executable"
    exit 1
fi
echo "PASS: scripts/redeploy.sh exists"

# Check prune.sh help (dry-run mode check)
if "$SCRIPT_DIR/scripts/prune.sh" --help >/dev/null 2>&1; then
    echo "PASS: prune.sh --help works"
else
    echo "WARN: prune.sh --help check failed"
fi

echo "=== Sanity check complete ==="
