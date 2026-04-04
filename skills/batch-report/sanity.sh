#!/usr/bin/env bash
# Sanity check for batch-report skill (modular version)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Sanity check for batch-report (modular) ==="

# Track failures
FAILED=0

check() {
    if "$@"; then
        echo "PASS: $1"
    else
        echo "FAIL: $1"
        FAILED=$((FAILED + 1))
    fi
}

# Check python3 exists
if ! command -v python3 >/dev/null 2>&1; then
    echo "FAIL: python3 not found"
    exit 1
fi
echo "PASS: python3 found"

# Check main script exists
if [[ ! -f "$SCRIPT_DIR/report.py" ]]; then
    echo "FAIL: report.py not found"
    exit 1
fi
echo "PASS: report.py exists"

# Check monolith backup exists
if [[ ! -f "$SCRIPT_DIR/report_monolith.py" ]]; then
    echo "WARN: report_monolith.py not found (original backup)"
fi

# Check SKILL.md exists
if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    exit 1
fi
echo "PASS: SKILL.md exists"

# Check modular package structure
MODULES=(
    "batch_report/__init__.py"
    "batch_report/config.py"
    "batch_report/utils.py"
    "batch_report/manifest_parser.py"
    "batch_report/analysis.py"
    "batch_report/markdown_generator.py"
)

for mod in "${MODULES[@]}"; do
    if [[ ! -f "$SCRIPT_DIR/$mod" ]]; then
        echo "FAIL: $mod not found"
        FAILED=$((FAILED + 1))
    else
        echo "PASS: $mod exists"
    fi
done

# Check module line counts (< 500 lines each)
echo ""
echo "=== Module Line Counts ==="
MAX_LINES=500
for mod in "${MODULES[@]}"; do
    if [[ -f "$SCRIPT_DIR/$mod" ]]; then
        lines=$(wc -l < "$SCRIPT_DIR/$mod")
        if [[ $lines -gt $MAX_LINES ]]; then
            echo "FAIL: $mod has $lines lines (max: $MAX_LINES)"
            FAILED=$((FAILED + 1))
        else
            echo "PASS: $mod has $lines lines"
        fi
    fi
done

# Check report.py line count
lines=$(wc -l < "$SCRIPT_DIR/report.py")
if [[ $lines -gt $MAX_LINES ]]; then
    echo "FAIL: report.py has $lines lines (max: $MAX_LINES)"
    FAILED=$((FAILED + 1))
else
    echo "PASS: report.py has $lines lines"
fi

echo ""
echo "=== Import Tests ==="

# Setup venv if needed and install dependencies
if [[ ! -d .venv ]]; then
    echo "Creating venv..."
    uv venv .venv
fi

# Install package in editable mode
source .venv/bin/activate
if [[ -f pyproject.toml ]]; then
    echo "Installing package..."
    uv pip install -e . 2>&1 | grep -v "already satisfied" || true
fi

# Test imports
if python3 -c "from batch_report.config import BatchFormat; print('OK')" 2>/dev/null; then
    echo "PASS: batch_report.config imports"
else
    echo "FAIL: batch_report.config import failed"
    FAILED=$((FAILED + 1))
fi

if python3 -c "from batch_report.utils import load_json; print('OK')" 2>/dev/null; then
    echo "PASS: batch_report.utils imports"
else
    echo "FAIL: batch_report.utils import failed"
    FAILED=$((FAILED + 1))
fi

if python3 -c "from batch_report.manifest_parser import find_manifests; print('OK')" 2>/dev/null; then
    echo "PASS: batch_report.manifest_parser imports"
else
    echo "FAIL: batch_report.manifest_parser import failed"
    FAILED=$((FAILED + 1))
fi

if python3 -c "from batch_report.analysis import analyze_failures; print('OK')" 2>/dev/null; then
    echo "PASS: batch_report.analysis imports"
else
    echo "FAIL: batch_report.analysis import failed"
    FAILED=$((FAILED + 1))
fi

if python3 -c "from batch_report.markdown_generator import generate_markdown_report; print('OK')" 2>/dev/null; then
    echo "PASS: batch_report.markdown_generator imports"
else
    echo "FAIL: batch_report.markdown_generator import failed"
    FAILED=$((FAILED + 1))
fi

echo ""
echo "=== CLI Tests ==="

# Check CLI help works
if python3 "$SCRIPT_DIR/report.py" --help >/dev/null 2>&1; then
    echo "PASS: CLI --help works"
else
    echo "FAIL: CLI --help failed"
    FAILED=$((FAILED + 1))
fi

# Check subcommands exist
for cmd in analyze summary failures state; do
    if python3 "$SCRIPT_DIR/report.py" "$cmd" --help >/dev/null 2>&1; then
        echo "PASS: CLI '$cmd' subcommand exists"
    else
        echo "FAIL: CLI '$cmd' subcommand missing"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
echo "=== Circular Import Check ==="
# Test for circular imports by importing all modules
if python3 -c "
from batch_report import config
from batch_report import utils
from batch_report import manifest_parser
from batch_report import analysis
from batch_report import markdown_generator
print('No circular imports detected')
" 2>/dev/null; then
    echo "PASS: No circular imports"
else
    echo "FAIL: Circular import detected"
    FAILED=$((FAILED + 1))
fi

echo ""
echo "=== Sanity check complete ==="
if [[ $FAILED -gt 0 ]]; then
    echo "RESULT: $FAILED check(s) failed"
    exit 1
else
    echo "RESULT: All checks passed"
    exit 0
fi
