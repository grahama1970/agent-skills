#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Arxiv Skill Sanity ==="

# Check run.sh exists
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [PASS] run.sh exists"
else
    echo "  [FAIL] run.sh missing"
    exit 1
fi

# Check run.sh --help works
if "$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1; then
    echo "  [PASS] run.sh --help works"
else
    echo "  [FAIL] run.sh --help failed"
    exit 1
fi

# Check all module files exist
MODULES=(config.py utils.py search.py download.py extraction.py memory_storage.py arxiv_learn.py)
for mod in "${MODULES[@]}"; do
    if [[ -f "$SCRIPT_DIR/$mod" ]]; then
        echo "  [PASS] $mod exists"
    else
        echo "  [FAIL] $mod missing"
        exit 1
    fi
done

# Check module line counts (all should be < 500)
echo ""
echo "=== Module Line Counts (must be < 500) ==="
MAX_LINES=500
OVER_LIMIT=0

for mod in "${MODULES[@]}"; do
    lines=$(wc -l < "$SCRIPT_DIR/$mod")
    if [[ $lines -lt $MAX_LINES ]]; then
        echo "  [PASS] $mod: $lines lines"
    else
        echo "  [FAIL] $mod: $lines lines (exceeds $MAX_LINES)"
        OVER_LIMIT=1
    fi
done

if [[ $OVER_LIMIT -eq 1 ]]; then
    echo ""
    echo "Result: FAIL (modules exceed line limit)"
    exit 1
fi

# Check Python syntax for all modules
echo ""
echo "=== Python Syntax Check ==="
for mod in "${MODULES[@]}"; do
    if python3 -m py_compile "$SCRIPT_DIR/$mod" 2>/dev/null; then
        echo "  [PASS] $mod syntax OK"
    else
        echo "  [FAIL] $mod syntax error"
        exit 1
    fi
done

# Check imports work (no circular dependencies)
echo ""
echo "=== Import Check (no circular imports) ==="

# Test each module can be imported independently
cd "$SCRIPT_DIR"
for mod in config utils search download extraction memory_storage arxiv_learn; do
    if python3 -c "import $mod" 2>/dev/null; then
        echo "  [PASS] import $mod"
    else
        echo "  [FAIL] import $mod failed"
        python3 -c "import $mod" 2>&1 | head -5
        exit 1
    fi
done

# Check monolith is preserved
if [[ -f "$SCRIPT_DIR/arxiv_learn_monolith.py" ]]; then
    echo "  [PASS] arxiv_learn_monolith.py preserved"
else
    echo "  [WARN] arxiv_learn_monolith.py not found (optional)"
fi

echo ""
echo "Result: PASS"
