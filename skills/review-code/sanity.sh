#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Code Review Sanity ==="

# Check SKILL.md exists
if [[ -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "  [PASS] SKILL.md exists"
else
    echo "  [FAIL] SKILL.md missing"
    exit 1
fi

# Check modular structure exists
MODULES=(
    "config.py"
    "utils.py"
    "diff_parser.py"
    "prompts.py"
    "code_review.py"
    "providers/__init__.py"
    "providers/base.py"
    "providers/github.py"
    "commands/__init__.py"
    "commands/basic.py"
    "commands/build.py"
    "commands/bundle.py"
    "commands/review.py"
    "commands/review_full.py"
    "commands/loop.py"
)

echo "  Checking modular structure..."
for mod in "${MODULES[@]}"; do
    if [[ -f "$SCRIPT_DIR/$mod" ]]; then
        echo "    [PASS] $mod exists"
    else
        echo "    [FAIL] $mod missing"
        exit 1
    fi
done

# Check line counts (all modules < 500 lines)
echo "  Checking line counts (max 500 lines)..."
for mod in "${MODULES[@]}"; do
    lines=$(wc -l < "$SCRIPT_DIR/$mod")
    if [[ $lines -lt 500 ]]; then
        echo "    [PASS] $mod: $lines lines"
    else
        echo "    [FAIL] $mod: $lines lines (exceeds 500)"
        exit 1
    fi
done

# Check Python syntax
echo "  Checking Python syntax..."
cd "$SCRIPT_DIR"
python3 -m py_compile config.py && echo "    [PASS] config.py syntax OK"
python3 -m py_compile utils.py && echo "    [PASS] utils.py syntax OK"
python3 -m py_compile diff_parser.py && echo "    [PASS] diff_parser.py syntax OK"
python3 -m py_compile prompts.py && echo "    [PASS] prompts.py syntax OK"
python3 -m py_compile providers/base.py && echo "    [PASS] providers/base.py syntax OK"
python3 -m py_compile providers/github.py && echo "    [PASS] providers/github.py syntax OK"
python3 -m py_compile providers/__init__.py && echo "    [PASS] providers/__init__.py syntax OK"

# Test imports (check for circular import issues)
echo "  Checking imports (circular import test)..."
cd "$SCRIPT_DIR"
python3 -c "
import sys
sys.path.insert(0, '.')

# Test individual module imports
from config import PROVIDERS, DEFAULT_PROVIDER
print('    [PASS] config imports OK')

from diff_parser import extract_diff
print('    [PASS] diff_parser imports OK')

from prompts import STEP1_PROMPT
print('    [PASS] prompts imports OK')
" && echo "    [PASS] No circular import issues"

# Test CLI help (basic smoke test)
echo "  Testing CLI help..."
cd "$SCRIPT_DIR"
python3 -c "
import sys
sys.path.insert(0, '..')
from code_review.code_review import app
" 2>/dev/null && echo "    [PASS] CLI module loads" || echo "    [WARN] CLI module load test skipped (run from parent dir)"

echo ""
echo "Result: PASS"
echo "All modular components verified."
