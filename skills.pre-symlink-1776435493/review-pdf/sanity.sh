#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [review-pdf] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1 - Required files: "
FAIL=0
for f in SKILL.md run.sh verify.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: missing $f"
        FAIL=1
    fi
done
if [[ ! -d "$SCRIPT_DIR/verify" ]]; then
    echo "FAIL: missing verify/ package directory"
    FAIL=1
fi
[[ $FAIL -eq 0 ]] && echo "PASS"
[[ $FAIL -ne 0 ]] && exit 1

# Check 2: uv available
echo -n "Check 2 - uv available: "
if command -v uv &>/dev/null; then
    echo "PASS"
else
    echo "FAIL: uv not found"
    exit 1
fi

# Check 3: Python syntax check on all .py files
echo -n "Check 3 - Python syntax: "
PY_FAIL=0
if ! python3 -m py_compile "$SCRIPT_DIR/verify.py" 2>/dev/null; then
    echo "FAIL: syntax error in verify.py"
    PY_FAIL=1
fi
for py in "$SCRIPT_DIR"/verify/*.py; do
    if [[ -f "$py" ]]; then
        if ! python3 -m py_compile "$py" 2>/dev/null; then
            echo "FAIL: syntax error in verify/$(basename "$py")"
            PY_FAIL=1
        fi
    fi
done
[[ $PY_FAIL -eq 0 ]] && echo "PASS"
[[ $PY_FAIL -ne 0 ]] && exit 1

# Check 4: verify package modules exist
echo -n "Check 4 - verify package modules: "
MODULES_FAIL=0
for mod in __init__.py cli.py models.py scoring.py analysis.py reporting.py escalation.py runner.py utils.py; do
    if [[ ! -f "$SCRIPT_DIR/verify/$mod" ]]; then
        echo "FAIL: missing verify/$mod"
        MODULES_FAIL=1
    fi
done
[[ $MODULES_FAIL -eq 0 ]] && echo "PASS"
[[ $MODULES_FAIL -ne 0 ]] && exit 1

# Check 5: Script dependencies (typer, pymupdf, loguru from inline deps)
echo -n "Check 5 - Core deps (typer, loguru): "
python3 -c "
import typer
from loguru import logger
print('PASS')
" || { echo "FAIL"; exit 1; }

echo -n "Check 5b - pymupdf: "
if python3 -c "import fitz" 2>/dev/null; then
    echo "PASS"
else
    echo "WARN: pymupdf not installed (needed for PDF processing)"
fi

# Check 6: run.sh help
echo -n "Check 6 - run.sh help: "
if bash "$SCRIPT_DIR/run.sh" help >/dev/null 2>&1; then
    echo "PASS"
else
    echo "WARN: run.sh help failed"
fi

# Check 7: YAML frontmatter
echo -n "Check 7 - SKILL.md frontmatter: "
if head -1 "$SCRIPT_DIR/SKILL.md" | grep -q '^---'; then
    echo "PASS"
else
    echo "FAIL: SKILL.md missing YAML frontmatter"
    exit 1
fi

echo ""
echo "SKIP: Full PDF audit (requires extractor corpus on 12TB)"
echo "SKIP: Memory event writing (requires writable memory sink)"
echo "SKIP: Escalation job execution (requires helper skills)"
echo ""
echo "Result: PASS"
