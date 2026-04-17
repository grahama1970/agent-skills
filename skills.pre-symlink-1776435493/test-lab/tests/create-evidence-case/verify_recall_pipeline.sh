#!/usr/bin/env bash
# Blind adversarial test: memory recall pipeline returns FULL results.
#
# Verifies that /create-evidence-case's recall path uses the FULL pipeline:
# - BM25 via ArangoSearch (lessons_search, sparta_qra_search)
# - Semantic/dense search (used_dense=true)
# - Supplemental sources (sparta_qras, lessons, etc.)
#
# This test exists because the daemon previously had broken defaults
# (collection="lessons", scope="general") that silently returned 0 items.
# The agent implementing /create-evidence-case must NEVER see this test.
set -euo pipefail

SOCKET="/run/user/$(id -u)/embry/memory.sock"
PASS=0
FAIL=0
TOTAL=0

check() {
    local id="$1" desc="$2"
    shift 2
    TOTAL=$((TOTAL + 1))
    if "$@" &>/dev/null 2>&1; then
        echo "  PASS  [$id] $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  [$id] $desc"
        FAIL=$((FAIL + 1))
    fi
}

check_json() {
    local id="$1" desc="$2" jq_expr="$3" payload="$4"
    TOTAL=$((TOTAL + 1))
    local output
    output=$(curl -s --unix-socket "$SOCKET" http://localhost/recall \
        -X POST -H 'Content-Type: application/json' -d "$payload" 2>&1) || true
    if echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); $jq_expr" 2>/dev/null; then
        echo "  PASS  [$id] $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  [$id] $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Memory Recall Full Pipeline Tests ==="
echo ""

# T1: Socket exists and daemon is reachable
check T1 "memory daemon socket exists" test -S "$SOCKET"

# T2: Health endpoint returns ok
check T2 "health endpoint returns ok" bash -c \
    "curl -sf --unix-socket '$SOCKET' http://localhost/health | grep -q '\"status\":\"ok\"'"

# T3: Recall returns >0 items for a known query (no collection filter)
check_json T3 "recall returns items without collection filter" \
    "assert len(d.get('items',[])) > 0, f'got {len(d.get(\"items\",[]))} items'" \
    '{"q":"boundary protection","limit":10}'

# T4: Recall returns items from MULTIPLE sources (not just one collection)
check_json T4 "recall returns items from multiple sources" \
    "
sources = set()
for i in d.get('items',[]):
    s = i.get('_collection', i.get('_source', i.get('source', '')))
    if s: sources.add(s)
assert len(sources) >= 2, f'only {sources} — need items from multiple sources'
" \
    '{"q":"boundary protection","limit":20}'

# T5: used_dense=true in meta (semantic search ran)
check_json T5 "semantic/dense search was used (used_dense=true)" \
    "assert d.get('meta',{}).get('used_dense') is True, f'used_dense={d.get(\"meta\",{}).get(\"used_dense\")}'" \
    '{"q":"How does SV-AC-2 protect avionics bus from spoofing?","limit":10}'

# T6: Items include sparta_qra results (supplemental source)
check_json T6 "sparta_qra supplemental source returns results" \
    "
qra_items = [i for i in d.get('items',[]) if i.get('control_id') or i.get('_collection')=='sparta_qras']
assert len(qra_items) > 0, 'no sparta_qra items found'
" \
    '{"q":"How does SV-AC-2 protect avionics bus from spoofing?","limit":20}'

# T7: Items include lessons results (BM25 primary lane)
check_json T7 "lessons source returns results" \
    "
lesson_items = [i for i in d.get('items',[]) if i.get('problem') or i.get('_collection')=='lessons']
assert len(lesson_items) > 0, 'no lesson items found'
" \
    '{"q":"boundary protection","limit":20}'

# T8: Empty scope doesn't default to "general" (which has 0 lessons)
check_json T8 "empty scope searches all scopes (not just general)" \
    "assert len(d.get('items',[])) > 5, f'only {len(d.get(\"items\",[]))} items with empty scope'" \
    '{"q":"boundary protection","limit":20}'

# T9: Confidence > 0 when items found
check_json T9 "confidence > 0 when items found" \
    "assert d.get('confidence', 0) > 0, f'confidence={d.get(\"confidence\",0)}'" \
    '{"q":"boundary protection","limit":10}'

# T10: No collection filter means >10 items (was 0 with old defaults)
check_json T10 "full pipeline returns >10 items (was 0 with broken defaults)" \
    "assert len(d.get('items',[])) > 10, f'got {len(d.get(\"items\",[]))} items'" \
    '{"q":"boundary protection","limit":50}'

echo ""
echo "=== Results: $PASS/$TOTAL passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL tests failed — recall pipeline is NOT using full BM25+semantic+supplemental"
    exit 1
fi
echo "PASS: Full recall pipeline verified (BM25 + semantic + multi-source)"
exit 0
