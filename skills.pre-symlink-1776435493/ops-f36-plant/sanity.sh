#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[sanity] Testing ops-f36-plant..."

# Check entry point exists
[ -x "$SKILL_DIR/run.sh" ] || { echo "FAIL: run.sh not found or not executable"; exit 1; }

# Check buttons.yaml exists (required for streamdeck integration)
[ -f "$SKILL_DIR/buttons.yaml" ] || { echo "FAIL: buttons.yaml not found"; exit 1; }

# Check for basic bash syntax
bash -n "$SKILL_DIR/run.sh" 2>/dev/null || { echo "FAIL: run.sh has syntax errors"; exit 1; }

echo "[sanity] ops-f36-plant: PASS"
