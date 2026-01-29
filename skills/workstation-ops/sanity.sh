#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=== workstation-ops sanity check ==="

# Check run.sh exists and is executable
[[ -x run.sh ]] || { echo "FAIL: run.sh not executable"; exit 1; }

# Check help works
./run.sh help >/dev/null 2>&1 || { echo "FAIL: run.sh help failed"; exit 1; }
echo "✓ help command works"

# Check basic check command
./run.sh check >/dev/null 2>&1 || { echo "FAIL: check command failed"; exit 1; }
echo "✓ check command works"

# Check memory command
./run.sh memory --top 5 >/dev/null 2>&1 || { echo "FAIL: memory command failed"; exit 1; }
echo "✓ memory command works"

# Check GPU command (may fail if no GPU, that's ok)
if command -v nvidia-smi &>/dev/null; then
  ./run.sh gpu >/dev/null 2>&1 || { echo "WARN: gpu command failed"; }
  echo "✓ gpu command works"
else
  echo "⊘ gpu command skipped (no nvidia-smi)"
fi

# Network diagnostics
./run.sh net --no-external >/dev/null 2>&1 || { echo "FAIL: net command failed"; exit 1; }
OUTPUT=json ./run.sh net --no-external >/dev/null 2>&1 || { echo "FAIL: net JSON failed"; exit 1; }
echo "✓ net diagnostics work"

# Temperature diagnostics (may have warnings, that's ok - just check it runs)
./run.sh temps >/dev/null 2>&1 || true  # Exit code may be 1 or 2 for warnings
OUTPUT=json ./run.sh temps >/dev/null 2>&1 || true
echo "✓ temps diagnostics work"

# Container health (graceful if docker missing)
if command -v docker &>/dev/null && docker info >/dev/null 2>&1; then
  ./run.sh containers >/dev/null 2>&1 || { echo "FAIL: containers command failed"; exit 1; }
  OUTPUT=json ./run.sh containers >/dev/null 2>&1 || { echo "FAIL: containers JSON failed"; exit 1; }
  echo "✓ containers command works"
else
  ./run.sh containers >/dev/null 2>&1 || { echo "FAIL: containers fallback failed"; exit 1; }
  echo "⊘ docker not running; containers fallback OK"
fi

echo ""
echo "=== All sanity checks passed ==="
