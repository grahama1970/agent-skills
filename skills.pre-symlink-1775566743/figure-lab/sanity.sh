#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[sanity] Testing figure-lab..."

# Check entry point exists
[ -x "$SKILL_DIR/run.sh" ] || { echo "FAIL: run.sh not found or not executable"; exit 1; }

# Check the actual monolith that run.sh invokes
[ -f "$SKILL_DIR/figure_lab.py" ] || { echo "FAIL: figure_lab.py not found"; exit 1; }

# Check Python syntax
python3 -c "import ast; ast.parse(open('$SKILL_DIR/figure_lab.py').read())" 2>/dev/null || { echo "FAIL: figure_lab.py has syntax errors"; exit 1; }

# Check evaluation.py exists and imports
[ -f "$SKILL_DIR/evaluation.py" ] || { echo "FAIL: evaluation.py not found"; exit 1; }
python3 -c "import ast; ast.parse(open('$SKILL_DIR/evaluation.py').read())" 2>/dev/null || { echo "FAIL: evaluation.py has syntax errors"; exit 1; }

# Check CLI loads (requires uv project deps)
cd "$SKILL_DIR"
uv run --project "$SKILL_DIR" python figure_lab.py --help >/dev/null 2>&1 || { echo "FAIL: figure_lab.py --help failed"; exit 1; }

# Check that /create-figure sibling exists (required dependency)
CREATE_FIGURE_DIR="$SKILL_DIR/../create-figure"
[ -d "$CREATE_FIGURE_DIR" ] || { echo "FAIL: sibling /create-figure not found"; exit 1; }
[ -f "$CREATE_FIGURE_DIR/d3_backend.py" ] || { echo "FAIL: d3_backend.py not found in /create-figure"; exit 1; }

echo "[sanity] figure-lab: PASS"
