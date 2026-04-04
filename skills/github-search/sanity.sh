#!/usr/bin/env bash
# Sanity check for github-search skill (modular version)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAX_LINES=500
FAIL_COUNT=0

echo "=== Sanity check for github-search ==="

# Check python3 exists
if ! command -v python3 >/dev/null 2>&1; then
    echo "FAIL: python3 not found"
    exit 1
fi
echo "PASS: python3 found"

# Check gh CLI exists
if ! command -v gh >/dev/null 2>&1; then
    echo "WARN: gh CLI not found (required for GitHub search)"
else
    echo "PASS: gh CLI found"
    # Check gh auth status
    if gh auth status >/dev/null 2>&1; then
        echo "PASS: gh authenticated"
    else
        echo "WARN: gh not authenticated (run: gh auth login)"
    fi
fi

# Check all module files exist
MODULES=("__init__.py" "config.py" "utils.py" "repo_search.py" "code_search.py" "readme_analyzer.py" "github_search.py")
echo ""
echo "--- Module existence check ---"
for module in "${MODULES[@]}"; do
    if [[ -f "$SCRIPT_DIR/$module" ]]; then
        echo "PASS: $module exists"
    else
        echo "FAIL: $module not found"
        ((FAIL_COUNT++))
    fi
done

# Check line counts (all modules < 500 lines)
echo ""
echo "--- Line count check (max $MAX_LINES lines per module) ---"
for module in "${MODULES[@]}"; do
    if [[ -f "$SCRIPT_DIR/$module" ]]; then
        line_count=$(wc -l < "$SCRIPT_DIR/$module")
        if [[ $line_count -le $MAX_LINES ]]; then
            echo "PASS: $module has $line_count lines"
        else
            echo "FAIL: $module has $line_count lines (exceeds $MAX_LINES)"
            ((FAIL_COUNT++))
        fi
    fi
done

# Check run.sh exists and is executable
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "WARN: run.sh not found or not executable"
else
    echo "PASS: run.sh exists and is executable"
fi

# Check SKILL.md exists
if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    ((FAIL_COUNT++))
else
    echo "PASS: SKILL.md exists"
fi

# Check Python syntax for all modules
echo ""
echo "--- Python syntax check ---"
SYNTAX_FAIL=0
for module in "${MODULES[@]}"; do
    if [[ -f "$SCRIPT_DIR/$module" ]]; then
        if python3 -m py_compile "$SCRIPT_DIR/$module" 2>&1; then
            echo "PASS: $module syntax OK"
        else
            echo "FAIL: $module has syntax errors"
            SYNTAX_FAIL=1
            ((FAIL_COUNT++))
        fi
    fi
done

# Check imports work when run as a package
echo ""
echo "--- Package import check ---"
# Create a temporary symlink with valid Python package name
TEMP_DIR=$(mktemp -d)
ln -s "$SCRIPT_DIR" "$TEMP_DIR/github_search"

if python3 -c "
import sys
sys.path.insert(0, '$TEMP_DIR')

try:
    # Import all modules through the package
    from github_search import config
    from github_search import utils
    from github_search import repo_search
    from github_search import code_search
    from github_search import readme_analyzer
    # Import main CLI module
    from github_search import github_search as main_cli
    print('PASS: All modules import successfully (no circular imports)')
except ImportError as e:
    print(f'FAIL: Import error: {e}')
    sys.exit(1)
except Exception as e:
    print(f'FAIL: Error: {e}')
    sys.exit(1)
" 2>&1; then
    :
else
    echo "FAIL: Package import check failed"
    ((FAIL_COUNT++))
fi

# Cleanup temp symlink
rm -rf "$TEMP_DIR"

# Check CLI app can be loaded
echo ""
echo "--- CLI functionality check ---"
TEMP_DIR2=$(mktemp -d)
ln -s "$SCRIPT_DIR" "$TEMP_DIR2/github_search"
if python3 -c "
import sys
sys.path.insert(0, '$TEMP_DIR2')
from github_search.github_search import app
print('PASS: CLI app imports successfully')
" 2>&1; then
    :
else
    echo "WARN: CLI app import check failed (may need dependencies)"
fi
rm -rf "$TEMP_DIR2"

# Summary
echo ""
echo "=== Sanity check complete ==="
if [[ $FAIL_COUNT -eq 0 ]]; then
    echo "All checks passed!"
    exit 0
else
    echo "FAILED: $FAIL_COUNT check(s) failed"
    exit 1
fi
