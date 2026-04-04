#!/usr/bin/env bash
# Sanity test for review-sparta skill
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

echo "=== review-sparta sanity test ==="

# 1. Check dependencies
echo "[1/4] Checking dependencies..."
if [[ ! -d ".venv" ]]; then
    uv venv .venv
    uv pip install typer rich duckdb httpx openpyxl
fi
source .venv/bin/activate
echo "  ✓ venv ready"

# 2. Check CLI help works
echo "[2/4] Checking CLI..."
python review_sparta.py --help > /dev/null
echo "  ✓ CLI works"

# 3. Check status command (dry run - may fail if no DB)
echo "[3/4] Checking status command..."
if python review_sparta.py status --run-id run-recovery-verify 2>/dev/null; then
    echo "  ✓ Status command works"
else
    echo "  ⚠ Status command failed (DB may not exist)"
fi

# 4. Check SKILL.md exists and has content
echo "[4/4] Checking SKILL.md..."
if [[ -f "SKILL.md" ]] && grep -q "Brandon Bailey" SKILL.md; then
    echo "  ✓ SKILL.md valid"
else
    echo "  ✗ SKILL.md missing or invalid"
    exit 1
fi

echo ""
echo "=== Sanity test PASSED ==="
