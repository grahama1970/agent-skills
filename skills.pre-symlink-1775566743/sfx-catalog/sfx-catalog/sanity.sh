#!/usr/bin/env bash
# Sanity checks for SFX catalog system

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== SFX Catalog Sanity Checks ==="

# Check 1: Python imports
echo "  [1/3] Testing Python imports..."
if .venv/bin/python -c "import librosa, soundfile, scipy, numpy, typer, rich" 2>/dev/null; then
    echo "  [PASS] All required Python libraries importable"
else
    echo "  [FAIL] Python import failed"
    exit 1
fi

# Check 2: ArangoDB connectivity
echo "  [2/3] Testing ArangoDB connectivity..."
if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8529/_api/version | grep -qE "200|401"; then
    echo "  [PASS] ArangoDB accessible"
else
    echo "  [WARN] ArangoDB not accessible (will degrade gracefully)"
fi

# Check 3: Status command
echo "  [3/3] Testing status command..."
if ./run.sh status >/dev/null 2>&1; then
    echo "  [PASS] Status command works"
else
    echo "  [FAIL] Status command failed"
    exit 1
fi

echo "=== All checks passed ==="
