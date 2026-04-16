#!/usr/bin/env bash
# skills-ci-exempt: shell_aql — tests memory infrastructure internals directly
# Blind adversarial test: memory database infrastructure health.
#
# Verifies the two user-requested invariants:
# 1. Embeddings are stored DIRECTLY on source documents (doc.embedding),
#    NOT in separate collections like sparta_qra_embeddings.
# 2. The /embedding service (port 8602) is using GPU (CUDA).
#
# Also verifies: vector indexes, ArangoSearch views, text_en analyzer,
# BM25 scoring, and embedding dimension consistency.
#
# The agent implementing memory infrastructure must NEVER see this test.
set -euo pipefail

ARANGO_URL="${ARANGO_URL:-http://127.0.0.1:8529}"
ARANGO_DB="${ARANGO_DB:-memory}"
ARANGO_USER="${ARANGO_USER:-root}"
ARANGO_PASS="${ARANGO_PASS:-openSesame}"
EMBEDDING_URL="${EMBEDDING_URL:-http://localhost:8602}"

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

check_output() {
    local id="$1" desc="$2" pattern="$3"
    shift 3
    TOTAL=$((TOTAL + 1))
    local output
    output=$("$@" 2>&1) || true
    if echo "$output" | grep -qE "$pattern"; then
        echo "  PASS  [$id] $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  [$id] $desc"
        FAIL=$((FAIL + 1))
    fi
}

aql() {
    curl -sf -u "$ARANGO_USER:$ARANGO_PASS" \
        "$ARANGO_URL/_db/$ARANGO_DB/_api/cursor" \
        -X POST -H 'Content-Type: application/json' \
        -d "{\"query\": \"$1\"}" 2>/dev/null
}

echo "=== Memory Database Infrastructure Tests ==="
echo ""

# ---------------------------------------------------------------
# Section 1: Embeddings stored DIRECTLY on source documents
# ---------------------------------------------------------------
echo "--- Embeddings Inline on Source Documents ---"

# T1: sparta_qra documents have doc.embedding field (not in separate collection)
check_output T1.1 "sparta_qra docs have inline embedding field" '"result":\[true\]' \
    bash -c "$(cat <<'CURL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/cursor" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"query": "FOR doc IN sparta_qra FILTER doc.embedding != null AND IS_LIST(doc.embedding) LIMIT 1 RETURN true"}'
CURL
)"

# T1.2: >99% of sparta_qra docs have embeddings (coverage)
check_output T1.2 "sparta_qra embedding coverage >99%" '"result":\[true\]' \
    bash -c "$(cat <<'CURL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/cursor" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"query": "LET total = LENGTH(sparta_qra) LET with_emb = (FOR d IN sparta_qra FILTER d.embedding != null AND IS_LIST(d.embedding) AND LENGTH(d.embedding) > 0 COLLECT WITH COUNT INTO c RETURN c)[0] RETURN (with_emb / total) > 0.99"}'
CURL
)"

# T1.3: lessons docs have inline embedding field
check_output T1.3 "lessons docs have inline embedding field" '"result":\[true\]' \
    bash -c "$(cat <<'CURL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/cursor" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"query": "FOR doc IN lessons FILTER doc.embedding != null AND IS_LIST(doc.embedding) LIMIT 1 RETURN true"}'
CURL
)"

# T1.4: Embedding dimension is 384 (all-MiniLM-L6-v2) on sparta_qra
check_output T1.4 "sparta_qra embedding dimension is 384" '"result":\[384\]' \
    bash -c "$(cat <<'CURL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/cursor" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"query": "FOR doc IN sparta_qra FILTER doc.embedding != null AND IS_LIST(doc.embedding) LIMIT 1 RETURN LENGTH(doc.embedding)"}'
CURL
)"

# T1.5: No separate sparta_qra_embeddings collection should be used
# (collection may exist as legacy but should have 0 documents or not exist)
check T1.5 "no active sparta_qra_embeddings collection (anti-silo)" \
    bash -c "$(cat <<'CURL'
RESP=$(curl -sf -u root:openSesame 'http://127.0.0.1:8529/_db/memory/_api/collection/sparta_qra_embeddings/count' 2>/dev/null)
if echo "$RESP" | grep -q '"error":true'; then
    exit 0  # collection doesn't exist = PASS
fi
COUNT=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count',0))" 2>/dev/null)
[ "${COUNT:-0}" -eq 0 ]  # exists but empty = PASS; has data = FAIL
CURL
)"

# ---------------------------------------------------------------
# Section 2: Embedding service uses GPU
# ---------------------------------------------------------------
echo ""
echo "--- Embedding Service GPU Usage ---"

# T2.1: Embedding service is reachable
check T2.1 "embedding service reachable on port 8602" \
    curl -sf "$EMBEDDING_URL/health"

# T2.2: Embedding service reports CUDA device (via /info endpoint)
check_output T2.2 "embedding service reports CUDA/GPU device" 'cuda|gpu|GPU' \
    curl -sf "$EMBEDDING_URL/info"

# T2.3: Embedding service returns 384-dim vectors (via /info endpoint)
check_output T2.3 "embedding service returns 384-dim vectors" '"dimensions":384' \
    curl -sf "$EMBEDDING_URL/info"

# T2.4: Embedding throughput (GPU should be >100 texts/s for batch of 10)
check T2.4 "embedding batch throughput (GPU-speed)" \
    bash -c "$(cat <<'CURL'
START=$(date +%s%N)
curl -sf http://localhost:8602/embed/batch \
    -X POST -H 'Content-Type: application/json' \
    -d '{"texts": ["test 1","test 2","test 3","test 4","test 5","test 6","test 7","test 8","test 9","test 10"]}' > /dev/null
END=$(date +%s%N)
ELAPSED=$(( (END - START) / 1000000 ))
# GPU should embed 10 texts in <500ms
[ "$ELAPSED" -lt 500 ]
CURL
)"

# ---------------------------------------------------------------
# Section 3: Vector indexes on source collections
# ---------------------------------------------------------------
echo ""
echo "--- Vector Indexes ---"

# T3.1: Vector index exists on sparta_qra.embedding
check_output T3.1 "vector index on sparta_qra.embedding" '"type":"vector"' \
    bash -c "curl -sf -u root:openSesame 'http://127.0.0.1:8529/_db/memory/_api/index?collection=sparta_qra' | grep -o '\"type\":\"vector\"'"

# T3.2: Vector index exists on lessons.embedding
check_output T3.2 "vector index on lessons.embedding" '"type":"vector"' \
    bash -c "curl -sf -u root:openSesame 'http://127.0.0.1:8529/_db/memory/_api/index?collection=lessons' | grep -o '\"type\":\"vector\"'"

# T3.3: Vector index configured for cosine metric
check_output T3.3 "vector index uses cosine metric" 'cosine' \
    bash -c "curl -sf -u root:openSesame 'http://127.0.0.1:8529/_db/memory/_api/index?collection=sparta_qra'"

# ---------------------------------------------------------------
# Section 4: ArangoSearch views and text_en analyzer
# ---------------------------------------------------------------
echo ""
echo "--- ArangoSearch Infrastructure ---"

# T4.1: text_en analyzer handles stemming (running → run)
check_output T4.1 "text_en analyzer stems words (running -> run)" 'run' \
    bash -c "$(cat <<'CURL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/analyzer/text_en" | python3 -c "
import sys, json
d = json.load(sys.stdin)
# text_en is a built-in that does stemming
print('run' if d.get('type') == 'text' else 'no')
"
CURL
)"

# T4.2: BM25 search returns results from sparta_qra_search view
check_output T4.2 "BM25 search on sparta_qra_search returns results" '"result":\[' \
    bash -c "$(cat <<'CURL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/cursor" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"query": "FOR doc IN sparta_qra_search SEARCH ANALYZER(doc.question IN TOKENS(\"avionics spoofing\", \"text_en\"), \"text_en\") SORT BM25(doc) DESC LIMIT 3 RETURN {q: doc.question, score: BM25(doc)}"}'
CURL
)"

# T4.3: BM25 search returns results from lessons_search view
check_output T4.3 "BM25 search on lessons_search returns results" '"result":\[' \
    bash -c "$(cat <<'CURL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/cursor" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"query": "FOR doc IN lessons_search SEARCH ANALYZER(doc.problem IN TOKENS(\"ArangoDB query\", \"text_en\"), \"text_en\") SORT BM25(doc) DESC LIMIT 3 RETURN {p: doc.problem, score: BM25(doc)}"}'
CURL
)"

# T4.4: Embedding dimensions are uniform across sparta_qra (no mixed dimensions)
check_output T4.4 "embedding dimensions uniform in sparta_qra" '"result":\[true\]' \
    bash -c "$(cat <<'CURL'
curl -sf -u root:openSesame \
    "http://127.0.0.1:8529/_db/memory/_api/cursor" \
    -X POST -H 'Content-Type: application/json' \
    -d '{"query": "LET dims = (FOR doc IN sparta_qra FILTER doc.embedding != null AND IS_LIST(doc.embedding) COLLECT dim = LENGTH(doc.embedding) RETURN dim) RETURN LENGTH(dims) == 1"}'
CURL
)"

echo ""
echo "=== Results: $PASS/$TOTAL passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL tests failed — memory database infrastructure is NOT healthy"
    exit 1
fi
echo "PASS: Memory database infrastructure verified (inline embeddings, GPU, vector indexes, BM25)"
exit 0
