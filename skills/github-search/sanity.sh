#!/usr/bin/env bash
# Sanity check for github-search skill.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAX_LINES=500
FAIL_COUNT=0
MODULES=(
    "__init__.py"
    "config.py"
    "utils.py"
    "repo_search.py"
    "code_search.py"
    "readme_analyzer.py"
    "candidate_search.py"
    "repo_runtime.py"
    "repo_evaluator.py"
    "evaluate_repos.py"
    "github_search.py"
)

echo "=== Sanity check for github-search ==="

if ! command -v python3 >/dev/null 2>&1; then
    echo "FAIL: python3 not found"
    exit 1
fi
echo "PASS: python3 found"

if ! command -v gh >/dev/null 2>&1; then
    echo "WARN: gh CLI not found (required for GitHub search)"
elif gh auth status >/dev/null 2>&1; then
    echo "PASS: gh authenticated"
else
    echo "WARN: gh not authenticated (run: gh auth login)"
fi

if [[ -f "$SCRIPT_DIR/../brave-search/run.sh" ]]; then
    echo "PASS: sibling brave-search skill found"
else
    echo "FAIL: sibling brave-search skill not found"
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

echo ""
echo "--- Module existence check ---"
for module in "${MODULES[@]}"; do
    if [[ -f "$SCRIPT_DIR/$module" ]]; then
        echo "PASS: $module exists"
    else
        echo "FAIL: $module not found"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

echo ""
echo "--- Line count check (max $MAX_LINES lines per module) ---"
for module in "${MODULES[@]}"; do
    if [[ -f "$SCRIPT_DIR/$module" ]]; then
        line_count=$(wc -l < "$SCRIPT_DIR/$module")
        if [[ $line_count -le $MAX_LINES ]]; then
            echo "PASS: $module has $line_count lines"
        else
            echo "FAIL: $module has $line_count lines (exceeds $MAX_LINES)"
            FAIL_COUNT=$((FAIL_COUNT + 1))
        fi
    fi
done

if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "WARN: run.sh not found or not executable"
else
    echo "PASS: run.sh exists and is executable"
fi

if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    FAIL_COUNT=$((FAIL_COUNT + 1))
else
    echo "PASS: SKILL.md exists"
fi

echo ""
echo "--- Python syntax check ---"
for module in "${MODULES[@]}"; do
    if [[ -f "$SCRIPT_DIR/$module" ]]; then
        if python3 -m py_compile "$SCRIPT_DIR/$module" 2>&1; then
            echo "PASS: $module syntax OK"
        else
            echo "FAIL: $module has syntax errors"
            FAIL_COUNT=$((FAIL_COUNT + 1))
        fi
    fi
done

echo ""
echo "--- Package import check ---"
if PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}" python3 -c "
import candidate_search
import code_search
import config
import evaluate_repos
import github_search
import readme_analyzer
import repo_evaluator
import repo_runtime
import repo_search
import utils
print('PASS: All modules import successfully')
" 2>&1; then
    :
else
    echo "FAIL: Package import check failed"
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

echo ""
echo "--- Offline pipeline smoke check ---"
if PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}" python3 - <<'PY'
import tempfile
from pathlib import Path

from candidate_search import extract_github_repository
from repo_evaluator import find_relevant_code
from repo_runtime import detect_entrypoint

assert extract_github_repository("https://github.com/owner/repo/blob/main/src/app.py") == "owner/repo"
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / "main.py").write_text(
        "def oauth_device_flow():\n    return 'device code'\n\n"
        "if __name__ == '__main__':\n    print('ok')\n",
        encoding="utf-8",
    )
    entrypoint = detect_entrypoint(root)
    assert entrypoint and entrypoint["command"][:2] == ["python3", "main.py"]
    evidence = find_relevant_code(root, "oauth device flow")
    assert evidence["matched_files"] == ["main.py"]
print("PASS: URL normalization, entry-point detection, and local evidence search")
PY
then
    :
else
    echo "FAIL: Offline pipeline smoke check failed"
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

echo ""
echo "--- CLI functionality check ---"
if PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}" python3 -c "
from github_search import app
from evaluate_repos import main
print('PASS: CLI entry points import successfully')
" 2>&1; then
    :
else
    echo "WARN: CLI import check failed (dependencies may be missing)"
fi

echo ""
echo "=== Sanity check complete ==="
if [[ $FAIL_COUNT -eq 0 ]]; then
    echo "All checks passed!"
    exit 0
fi
echo "FAILED: $FAIL_COUNT check(s) failed"
exit 1
