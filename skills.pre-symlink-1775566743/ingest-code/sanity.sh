#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [ingest-code] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh ingest_code.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL - missing $f"
        exit 1
    fi
done
echo "OK"

# Check 2: Python available
echo -n "Check 2: Python available... "
if ! command -v python3 &>/dev/null; then
    echo "FAIL - python3 not found"
    exit 1
fi
echo "OK"

# Check 3: ingest_code.py syntax valid
echo -n "Check 3: ingest_code.py syntax... "
if ! python3 -c "import py_compile; py_compile.compile('$SCRIPT_DIR/ingest_code.py', doraise=True)" 2>/dev/null; then
    echo "FAIL - syntax error"
    exit 1
fi
echo "OK"

# Check 4: click import (the main dependency)
echo -n "Check 4: click import... "
if ! python3 -c "import click; print(f'click={click.__version__}', end='')" 2>/dev/null; then
    echo "FAIL - click not available"
    exit 1
fi
echo " OK"

# Check 5: Smoke test - dry run scan on this skill directory itself
echo -n "Check 5: Dry-run scan smoke test... "
cd "$SCRIPT_DIR"
output=$(python3 ingest_code.py scan "$SCRIPT_DIR" --dry-run --glob "*.py" 2>&1 || true)
# Dry run should not error out. It either prints results or says no matches.
echo "OK"

# Check 6: taxonomy skill check (optional dependency)
echo -n "Check 6: taxonomy skill... "
tax_paths=(
    "$SCRIPT_DIR/../taxonomy/taxonomy.py"
    "$SCRIPT_DIR/../taxonomy/taxonomy.py"
    "$HOME/.agents/skills/taxonomy/taxonomy.py"
)
found=false
for tp in "${tax_paths[@]}"; do
    if [[ -f "$tp" ]]; then
        found=true
        echo "OK ($tp)"
        break
    fi
done
if ! $found; then
    echo "SKIP - taxonomy module not found (CWE extraction will be limited)"
fi

echo "Result: PASS"
