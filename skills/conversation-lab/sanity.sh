#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== conversation-lab sanity ==="

# 1. py_compile
echo "1. Checking syntax..."
python3 -m py_compile conversation_lab.py
echo "   PASS: syntax ok"

# 2. Import check
echo "2. Checking imports..."
python3 -c "from conversation_lab import app; print('   PASS: imports ok')"

# 3. CLI --help
echo "3. Checking CLI..."
uv run --project "$SCRIPT_DIR" python conversation_lab.py --help > /dev/null 2>&1
echo "   PASS: CLI ok"

# 4. Subcommand help
for cmd in diagnose report data converge optimize status; do
    uv run --project "$SCRIPT_DIR" python conversation_lab.py "$cmd" --help > /dev/null 2>&1
    echo "   PASS: $cmd --help ok"
done

# 5. Line count
LINES=$(wc -l < conversation_lab.py)
if [ "$LINES" -gt 800 ]; then
    echo "   FAIL: conversation_lab.py is $LINES lines (max 800)"
    exit 1
fi
echo "   PASS: $LINES lines (max 800)"

# 6. Module docstring check
HEAD=$(head -1 conversation_lab.py)
if [[ "$HEAD" != '"""'* ]]; then
    echo "   FAIL: missing module docstring"
    exit 1
fi
echo "   PASS: module docstring present"

echo "=== All sanity checks passed ==="
