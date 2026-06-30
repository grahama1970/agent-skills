#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [data-audit] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1 - Required files: "
FAIL=0
for f in SKILL.md audit.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: missing $f"
        FAIL=1
    fi
done
[[ $FAIL -eq 0 ]] && echo "PASS"
[[ $FAIL -ne 0 ]] && exit 1

# Check 2: Python syntax check
echo -n "Check 2 - Python syntax: "
if python3 -m py_compile "$SCRIPT_DIR/audit.py" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL: syntax error in audit.py"
    exit 1
fi

# Check 3: Required imports
echo -n "Check 3 - duckdb import: "
if python3 -c "import duckdb" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL: duckdb not installed (pip install duckdb)"
    exit 1
fi

echo -n "Check 3b - rich import: "
if python3 -c "from rich.console import Console; from rich.table import Table" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL: rich not installed (pip install rich)"
    exit 1
fi

# Check 4: Smoke test - CLI help
echo -n "Check 4 - CLI help: "
if python3 "$SCRIPT_DIR/audit.py" --help >/dev/null 2>&1; then
    echo "PASS"
else
    echo "FAIL: audit.py --help failed"
    exit 1
fi

# Check 5: DB file check (WARN only, DB may not exist in all envs)
echo -n "Check 5 - SPARTA DB: "
DB_PATH="${HOME}/workspace/experiments/sparta/data/runs/run-recovery-verify/sparta.duckdb"
if [[ -f "$DB_PATH" ]]; then
    echo "PASS (found)"
else
    echo "WARN: DB not found at $DB_PATH (audit will fail at runtime)"
fi

# Check 6: YAML frontmatter
echo -n "Check 6 - SKILL.md frontmatter: "
if head -1 "$SCRIPT_DIR/SKILL.md" | grep -q '^---'; then
    echo "PASS"
else
    echo "FAIL: SKILL.md missing YAML frontmatter"
    exit 1
fi

echo ""
echo "Result: PASS"
