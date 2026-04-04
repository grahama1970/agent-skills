#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== create-context sanity check ==="

# Check Python file syntax
echo "Checking Python syntax..."
python3 -m py_compile context.py
echo "  context.py: OK"

# Check run.sh is executable
if [[ -x run.sh ]]; then
    echo "  run.sh: executable"
else
    echo "  run.sh: NOT executable"
    exit 1
fi

# Check pyproject.toml exists
if [[ -f pyproject.toml ]]; then
    echo "  pyproject.toml: exists"
else
    echo "  pyproject.toml: MISSING"
    exit 1
fi

# Check SKILL.md exists
if [[ -f SKILL.md ]]; then
    echo "  SKILL.md: exists"
else
    echo "  SKILL.md: MISSING"
    exit 1
fi

echo ""
echo "All checks passed!"
