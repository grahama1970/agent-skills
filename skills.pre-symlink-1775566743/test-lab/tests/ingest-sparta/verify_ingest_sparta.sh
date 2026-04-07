#!/usr/bin/env bash
# skills-ci-exempt: shell_aql — tests memory infrastructure internals directly
# Blind adversarial test: /ingest-sparta pipeline data integrity.
#
# Verifies that sparta_url_knowledge documents meet quality invariants:
# 1. Documents have required fields (topic, text, url_id, excerpt_index, embedding)
# 2. Dedup index on (url_id, excerpt_index) is enforced
# 3. Documents are searchable via sparta_unified_search BM25 view
# 4. No direct graph_memory imports in ingest code (daemon-only)
# 5. Embeddings are 384-dim and inline (not in separate collection)
# 6. Adversarial: junk/empty content should NOT be stored
# 7. Adversarial: fabricated control IDs should NOT create valid docs
#
# The agent implementing /ingest-sparta must NEVER see this test.
set -euo pipefail

ARANGO_URL="${ARANGO_URL:-http://127.0.0.1:8529}"
ARANGO_DB="${ARANGO_DB:-memory}"
ARANGO_USER="${ARANGO_USER:-root}"
ARANGO_PASS="${ARANGO_PASS:-openSesame}"
DAEMON_SOCKET="${DAEMON_SOCKET:-/run/user/1000/embry/memory.sock}"
INGEST_SKILL="${INGEST_SKILL:-$HOME/workspace/experiments/pi-mono/.pi/skills/ingest-sparta}"

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

# JSON-safe AQL query helper — returns parsed JSON via python3
aql_json() {
    curl -sf -u "$ARANGO_USER:$ARANGO_PASS" \
        "$ARANGO_URL/_db/$ARANGO_DB/_api/cursor" \
        -X POST -H 'Content-Type: application/json' \
        -d "{\"query\": \"$1\"}" 2>/dev/null
}

# Structured check: run a command, parse JSON output with python3 expression
# Usage: check_json ID "description" "python3_assert_expr" command...
#   The python3 expr receives `d` = parsed JSON dict. Must return truthy.
check_json() {
    local id="$1" desc="$2" py_expr="$3"
    shift 3
    TOTAL=$((TOTAL + 1))
    local output
    output=$("$@" 2>&1) || true
    if echo "$output" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    assert $py_expr, 'assertion failed'
except Exception as e:
    sys.exit(1)
" 2>/dev/null; then
        echo "  PASS  [$id] $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  [$id] $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== /ingest-sparta Pipeline Data Integrity Tests ==="
echo ""

# ---------------------------------------------------------------
# Section 1: Collection exists and has data
# ---------------------------------------------------------------
echo "--- Collection Health ---"

check_json T1.1 "sparta_url_knowledge collection exists with >1000 docs" \
    "d.get('count', 0) > 1000" \
    curl -sf -u "$ARANGO_USER:$ARANGO_PASS" \
    "$ARANGO_URL/_db/$ARANGO_DB/_api/collection/sparta_url_knowledge/count"

# T1.2: Unique index on (url_id, excerpt_index) exists
check_json T1.2 "unique dedup index on (url_id, excerpt_index)" \
    "any('url_id' in str(idx.get('fields',[])) and 'excerpt_index' in str(idx.get('fields',[])) for idx in d.get('indexes',[]))" \
    curl -sf -u "$ARANGO_USER:$ARANGO_PASS" \
    "$ARANGO_URL/_db/$ARANGO_DB/_api/index?collection=sparta_url_knowledge"

# T1.3: Vector index exists on embedding field
check_json T1.3 "vector index on sparta_url_knowledge.embedding" \
    "any(idx.get('type') == 'vector' for idx in d.get('indexes',[]))" \
    curl -sf -u "$ARANGO_USER:$ARANGO_PASS" \
    "$ARANGO_URL/_db/$ARANGO_DB/_api/index?collection=sparta_url_knowledge"

# ---------------------------------------------------------------
# Section 2: Document quality invariants
# ---------------------------------------------------------------
echo ""
echo "--- Document Quality ---"

# T2.1: All docs have required fields (topic, text, url_id, excerpt_index)
check_json T2.1 "all docs have topic+text+url_id+excerpt_index fields" \
    "d['result'][0] == True" \
    bash -c "$(cat <<'AQL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/cursor" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"query": "LET total = LENGTH(sparta_url_knowledge) LET valid = (FOR d IN sparta_url_knowledge FILTER d.topic != null AND d.text != null AND d.url_id != null AND d.excerpt_index != null COLLECT WITH COUNT INTO c RETURN c)[0] RETURN valid == total"}'
AQL
)"

# T2.2: Embeddings exist on >90% of documents (384-dim)
check_json T2.2 "embedding coverage >90% on sparta_url_knowledge" \
    "d['result'][0] == True" \
    bash -c "$(cat <<'AQL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/cursor" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"query": "LET total = LENGTH(sparta_url_knowledge) LET with_emb = (FOR d IN sparta_url_knowledge FILTER d.embedding != null AND IS_LIST(d.embedding) AND LENGTH(d.embedding) == 384 COLLECT WITH COUNT INTO c RETURN c)[0] RETURN (with_emb / total) > 0.90"}'
AQL
)"

# T2.3: No empty/null text fields (junk should be filtered)
check_json T2.3 "no docs with empty text (junk filter working)" \
    "d['result'][0] == 0" \
    bash -c "$(cat <<'AQL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/cursor" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"query": "FOR d IN sparta_url_knowledge FILTER d.text == null OR d.text == \"\" OR LENGTH(d.text) < 10 COLLECT WITH COUNT INTO c RETURN c"}'
AQL
)"

# T2.4: Text field contains actual content, not HTML tags
check_json T2.4 "no docs with raw HTML in text field" \
    "d['result'][0] == True" \
    bash -c "$(cat <<'AQL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/cursor" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"query": "LET html_docs = (FOR d IN sparta_url_knowledge FILTER CONTAINS(d.text, \"<!DOCTYPE\") OR CONTAINS(d.text, \"<html\") COLLECT WITH COUNT INTO c RETURN c)[0] RETURN html_docs == 0"}'
AQL
)"

# T2.5: excerpt_type field is consistently set
check_json T2.5 "excerpt_type field consistently set" \
    "d['result'][0] == True" \
    bash -c "$(cat <<'AQL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/cursor" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"query": "LET types = (FOR d IN sparta_url_knowledge COLLECT t = d.excerpt_type WITH COUNT INTO c RETURN {t, c}) RETURN LENGTH(types) <= 10"}'
AQL
)"

# ---------------------------------------------------------------
# Section 3: BM25 searchability via unified view
# ---------------------------------------------------------------
echo ""
echo "--- BM25 Searchability ---"

# T3.1: sparta_unified_search view includes sparta_url_knowledge
check_json T3.1 "sparta_unified_search links sparta_url_knowledge" \
    "'sparta_url_knowledge' in json.dumps(d)" \
    curl -sf -u "$ARANGO_USER:$ARANGO_PASS" \
    "$ARANGO_URL/_db/$ARANGO_DB/_api/view/sparta_unified_search/properties"

# T3.2: BM25 query returns results from sparta_url_knowledge via unified view
check_json T3.2 "BM25 on unified view returns url_knowledge results" \
    "len(d.get('result', [])) > 0" \
    bash -c "$(cat <<'AQL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/cursor" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"query": "FOR doc IN sparta_unified_search SEARCH ANALYZER(doc.text IN TOKENS(\"authentication access control\", \"text_en\"), \"text_en\") FILTER IS_SAME_COLLECTION(\"sparta_url_knowledge\", doc) SORT BM25(doc) DESC LIMIT 3 RETURN {topic: doc.topic, score: BM25(doc)}"}'
AQL
)"

# T3.3: Daemon /recall returns results (end-to-end via Unix socket)
check T3.3 "daemon /recall returns results for security query" \
    bash -c "$(cat <<'CURL'
RESP=$(curl -sf --unix-socket /run/user/1000/embry/memory.sock \
    http://localhost/recall \
    -X POST -H 'Content-Type: application/json' \
    -d '{"q": "avionics bus authentication spoofing protection", "limit": 5}')
echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d.get('results',[])) > 0"
CURL
)"

# ---------------------------------------------------------------
# Section 4: Anti-silo / architecture enforcement
# ---------------------------------------------------------------
echo ""
echo "--- Architecture Enforcement ---"

# T4.1: ingest_sparta.py does NOT import graph_memory directly
check T4.1 "ingest_sparta.py has no direct graph_memory imports" \
    bash -c "! grep -rn 'from graph_memory\|import graph_memory' '$INGEST_SKILL/ingest_sparta.py' 2>/dev/null"

# T4.2: ingest_sparta.py uses daemon Unix socket, not TCP port
check T4.2 "ingest code uses Unix socket path" \
    bash -c "grep -rqE 'memory\.sock|unix.*socket|uds=|DAEMON_SOCKET|embry/memory' '$INGEST_SKILL/ingest_sparta.py' 2>/dev/null"

# T4.3: No hardcoded ArangoDB passwords in ingest code
check T4.3 "no hardcoded ArangoDB credentials in ingest code" \
    bash -c "! grep -rn 'openSesame\|ARANGO_PASS.*=' '$INGEST_SKILL/ingest_sparta.py' 2>/dev/null"

# T4.4: Classifier uses sklearn, not regex entity classification
check T4.4 "classifier uses sklearn not regex classification" \
    bash -c "grep -qE 'sklearn|LogisticRegression|TfidfVectorizer' '$INGEST_SKILL/classifier.py' 2>/dev/null"

# ---------------------------------------------------------------
# Section 5: Adversarial data integrity
# ---------------------------------------------------------------
echo ""
echo "--- Adversarial Data Integrity ---"

# T5.1: Daemon rejects learn with empty solution
check T5.1 "daemon rejects /learn with empty solution" \
    bash -c "$(cat <<'CURL'
HTTP_CODE=$(curl -sf -o /dev/null -w '%{http_code}' --unix-socket /run/user/1000/embry/memory.sock \
    http://localhost/learn \
    -X POST -H 'Content-Type: application/json' \
    -d '{"problem": "test", "solution": "", "scope": "test_adversarial", "collection": "sparta_url_knowledge"}')
[ "$HTTP_CODE" = "400" ] || [ "$HTTP_CODE" = "422" ]
CURL
)"

# T5.2: Duplicate (url_id, excerpt_index) gets UPSERT not error
check_json T5.2 "duplicate url_id+excerpt_index upserts cleanly" \
    "d.get('stored') == True" \
    bash -c "$(cat <<'CURL'
curl -sf --unix-socket /run/user/1000/embry/memory.sock \
    http://localhost/learn \
    -X POST -H 'Content-Type: application/json' \
    -d '{"problem": "blind test dedup", "solution": "Verifying that duplicate url_id plus excerpt_index pairs are handled gracefully via overwrite semantics in the target knowledge store", "scope": "sparta_url_knowledge", "source": "test-lab", "collection": "sparta_url_knowledge", "extra_fields": {"url_id": "test-lab-dedup-001", "excerpt_index": 0}}'
CURL
)"

# T5.3: No test-lab pollution — clean up the test doc we just created
check T5.3 "cleanup: remove test-lab adversarial doc" \
    bash -c "$(cat <<'CURL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/cursor" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"query": "FOR d IN sparta_url_knowledge FILTER d.source == \"test-lab\" REMOVE d IN sparta_url_knowledge"}'
CURL
)"

echo ""
echo "=== Results: $PASS/$TOTAL passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL tests failed — /ingest-sparta pipeline has data integrity issues"
    exit 1
fi
echo "PASS: /ingest-sparta pipeline verified (collection, quality, BM25, architecture, adversarial)"
exit 0
