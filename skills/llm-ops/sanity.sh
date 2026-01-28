#!/usr/bin/env bash
# Sanity check for llm-ops skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Sanity check for llm-ops ==="

# Check SKILL.md exists
if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    exit 1
fi
echo "PASS: SKILL.md exists"

# Check scripts exist and are executable
if [[ ! -x "$SCRIPT_DIR/scripts/health.sh" ]]; then
    echo "FAIL: scripts/health.sh not found or not executable"
    exit 1
fi
echo "PASS: scripts/health.sh exists"

if [[ ! -x "$SCRIPT_DIR/scripts/cache-clean.sh" ]]; then
    echo "FAIL: scripts/cache-clean.sh not found or not executable"
    exit 1
fi
echo "PASS: scripts/cache-clean.sh exists"

# Check health.sh help
if "$SCRIPT_DIR/scripts/health.sh" --help >/dev/null 2>&1; then
    echo "PASS: health.sh --help works"
else
    echo "WARN: health.sh --help check failed"
fi

# Check curl exists (used for health checks)
if ! command -v curl >/dev/null 2>&1; then
    echo "WARN: curl not found (required for health checks)"
else
    echo "PASS: curl found"
fi

echo "=== Sanity check complete ==="
