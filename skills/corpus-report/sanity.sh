#!/usr/bin/env bash
# sanity.sh -- Quick verification that corpus-report commands work.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PASS=0
FAIL=0

run_check() {
    local label="$1"
    shift
    printf "%-40s " "$label"
    if output=$("$@" 2>&1); then
        echo "PASS"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        echo "  Output: ${output:0:200}"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== corpus-report sanity ==="
echo ""

# 1. Summary JSON produces valid JSON with expected keys
run_check "summary --json parses" \
    bash -c './run.sh summary --json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert \"total\" in d, \"missing total\"; assert \"completed\" in d"'

# 2. Quality JSON produces valid JSON
run_check "quality --json parses" \
    bash -c './run.sh quality --json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert \"total_with_ratio\" in d"'

# 3. Patterns JSON produces valid JSON
run_check "patterns --json parses" \
    bash -c './run.sh patterns --json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert \"patterns\" in d"'

# 4. Bottlenecks JSON produces valid JSON
run_check "bottlenecks --json parses" \
    bash -c './run.sh bottlenecks --json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert \"files_sampled\" in d"'

# 5. Trends JSON produces valid JSON
run_check "trends --json parses" \
    bash -c './run.sh trends --json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert \"windows\" in d"'

# 6. Empty corpus (nonexistent CORPUS_ROOT) doesn't crash
run_check "empty corpus graceful" \
    bash -c 'CORPUS_ROOT=/tmp/nonexistent_corpus_42 ./run.sh summary --json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert d[\"total\"]==0"'

# 7. Category filter works without crash
run_check "category filter" \
    bash -c './run.sh summary --json --category nonexistent_cat 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert d[\"total\"]==0"'

# 8. Rich output (summary) runs without error
run_check "summary rich output" \
    bash -c './run.sh summary 2>/dev/null >/dev/null'

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
