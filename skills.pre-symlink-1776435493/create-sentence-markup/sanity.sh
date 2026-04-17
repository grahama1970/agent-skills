#!/usr/bin/env bash
# Sanity check for /create-sentence-markup
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== /create-sentence-markup sanity check ==="

# 1. Help text
echo "[1/4] Help text..."
"$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1
echo "  OK"

# 2. JSON output for fabricated ID
echo "[2/4] Fabricated ID detection (JSON)..."
result=$("$SCRIPT_DIR/run.sh" annotate "How does SPARTA control X23-MUSTARD mitigate spoofing?" --format json 2>/dev/null)
if echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); assert any(a['level']=='RED' for a in d['annotations']), 'No RED annotation'"; then
    echo "  OK — RED annotation found for fabricated ID"
else
    echo "  FAIL — no RED annotation"
    exit 1
fi

# 3. Markdown output
echo "[3/4] Markdown rendering..."
md=$("$SCRIPT_DIR/run.sh" annotate "How does the SPRTA framework work?" --format markdown 2>/dev/null)
if echo "$md" | grep -q "Did you mean"; then
    echo "  OK — misspelling annotation rendered"
else
    echo "  FAIL — no misspelling in markdown"
    exit 1
fi

# 4. Clarify command
echo "[4/4] Clarify command..."
clarify=$("$SCRIPT_DIR/run.sh" clarify "How does the SPRTA framework work?" 2>/dev/null)
if echo "$clarify" | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d.get('interview_questions',[])) > 0, 'No interview questions'" 2>/dev/null; then
    echo "  OK — interview questions generated"
else
    echo "  FAIL — no interview questions"
    exit 1
fi

echo ""
echo "=== All sanity checks passed ==="
