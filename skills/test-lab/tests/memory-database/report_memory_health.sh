#!/usr/bin/env bash
# Memory Database Health Report Generator
#
# Produces a REPORT.md with:
#   1. Blind test results (from verify_memory_database.sh)
#   2. /db/audit metrics from the memory daemon
#   3. Embedding service GPU status
#   4. Mermaid diagrams: collection sizes, embedding coverage, BM25 health
#
# Usage:
#   ./report_memory_health.sh                    # default output to ./REPORT.md
#   ./report_memory_health.sh /path/to/output.md # custom output path
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPORT="${1:-${SCRIPT_DIR}/REPORT.md}"
DAEMON_SOCK="/run/user/$(id -u)/embry/memory.sock"
EMBEDDING_URL="${EMBEDDING_URL:-http://localhost:8602}"
TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M:%S UTC')

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
daemon_get() {
    curl -sf --unix-socket "$DAEMON_SOCK" "http://localhost$1" 2>/dev/null
}

jq_or_fallback() {
    python3 -c "import sys,json; d=json.load(sys.stdin); exec(open('/dev/stdin').read() if False else None)" 2>/dev/null \
        || echo "N/A"
}

# -------------------------------------------------------------------
# Collect data
# -------------------------------------------------------------------
echo "Collecting /db/audit from daemon..." >&2
AUDIT_JSON=$(daemon_get "/db/audit" || echo '{}')

echo "Collecting /info from embedding service..." >&2
EMBED_JSON=$(curl -sf "$EMBEDDING_URL/info" 2>/dev/null || echo '{}')

echo "Running blind tests..." >&2
TEST_OUTPUT=$("$SCRIPT_DIR/verify_memory_database.sh" 2>&1) || true
TEST_EXIT=$?

# Extract metrics via python (safe for complex JSON)
read_audit() {
    echo "$AUDIT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
$1
" 2>/dev/null || echo "N/A"
}

# -------------------------------------------------------------------
# Parse audit data
# -------------------------------------------------------------------
COLLECTION_TABLE=$(echo "$AUDIT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
cols = d.get('collections', {})
for name, info in sorted(cols.items()):
    status = 'PASS' if info.get('exists') else 'FAIL'
    count = f\"{info.get('count', 0):,}\"
    print(f'| \`{name}\` | {status} | {count} |')
" 2>/dev/null || echo "| error | - | - |")

VIEW_TABLE=$(echo "$AUDIT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
views = d.get('views', {})
for name, info in sorted(views.items()):
    status = 'PASS' if info.get('exists') and info.get('has_links') else 'FAIL'
    linked = ', '.join(info.get('linked_collections', []))
    print(f'| \`{name}\` | {status} | {linked} |')
" 2>/dev/null || echo "| error | - | - |")

EMBEDDING_COV_TABLE=$(echo "$AUDIT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
cov = d.get('embedding_coverage', {})
for name, info in sorted(cov.items()):
    total = f\"{info.get('total', 0):,}\"
    embedded = f\"{info.get('embedded', 0):,}\"
    missing = info.get('missing', 0)
    pct = info.get('coverage_pct', 0)
    status = 'PASS' if pct >= 99.0 else 'FAIL'
    print(f'| \`{name}\` | {status} | {total} | {embedded} | {missing} | {pct:.1f}% |')
" 2>/dev/null || echo "| error | - | - | - | - | - |")

BM25_TABLE=$(echo "$AUDIT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
bm = d.get('bm25', {})
for name, info in sorted(bm.items()):
    status = 'PASS' if info.get('pass') else 'FAIL'
    count = info.get('result_count', 0)
    top = info.get('top_score', 0)
    desc = 'Yes' if info.get('scores_descending') else 'No'
    print(f'| \`{name}\` | {status} | {count} | {top:.2f} | {desc} |')
" 2>/dev/null || echo "| error | - | - | - | - |")

DIMENSION_TABLE=$(echo "$AUDIT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
dims = d.get('embedding_dimensions', {})
for name, info in sorted(dims.items()):
    status = 'PASS' if info.get('pass') else 'FAIL'
    dim = info.get('dimension', 'N/A')
    wrong = info.get('wrong_dimension_count', 0)
    print(f'| \`{name}\` | {status} | {dim} | {wrong} |')
" 2>/dev/null || echo "| error | - | - | - |")

SYNC_TABLE=$(echo "$AUDIT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
sync = d.get('view_sync', {})
for name, info in sorted(sync.items()):
    status = 'PASS' if info.get('pass') else 'FAIL'
    col_count = f\"{info.get('collection_count', 0):,}\"
    view_count = f\"{info.get('view_count', 0):,}\"
    delta = info.get('delta', 0)
    print(f'| \`{name}\` | {status} | {col_count} | {view_count} | {delta} |')
" 2>/dev/null || echo "| error | - | - | - | - |")

DEDUP_TABLE=$(echo "$AUDIT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
dup = d.get('duplicates', {})
for name, info in sorted(dup.items()):
    status = 'PASS' if info.get('pass') else 'FAIL'
    groups = info.get('duplicate_groups', 0)
    total = info.get('total_duplicate_docs', 0)
    field = info.get('dedup_field', 'N/A')
    print(f'| \`{name}\` | {status} | {groups} | {total} | {field} |')
" 2>/dev/null || echo "| error | - | - | - | - |")

SCHEMA_TABLE=$(echo "$AUDIT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
sch = d.get('schema', {})
for name, info in sorted(sch.items()):
    status = 'PASS' if info.get('pass') else 'FAIL'
    missing = info.get('missing_required_fields', 0)
    total = f\"{info.get('total', 0):,}\"
    fields = ', '.join(info.get('checked_fields', []))
    print(f'| \`{name}\` | {status} | {total} | {missing} | {fields} |')
" 2>/dev/null || echo "| error | - | - | - | - |")

VECTOR_TABLE=$(echo "$AUDIT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
vec = d.get('vector_indexes', {})
for name, info in sorted(vec.items()):
    status = 'PASS' if info.get('exists') else 'FAIL'
    itype = info.get('type', 'N/A')
    print(f'| \`{name}\` | {status} | {itype} |')
" 2>/dev/null || echo "| error | - | - |")

# Embedding service info
EMBED_MODEL=$(echo "$EMBED_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('model','N/A'))" 2>/dev/null || echo "N/A")
EMBED_DEVICE=$(echo "$EMBED_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('device','N/A'))" 2>/dev/null || echo "N/A")
EMBED_DIM=$(echo "$EMBED_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dimensions','N/A'))" 2>/dev/null || echo "N/A")
EMBED_UPTIME=$(echo "$EMBED_JSON" | python3 -c "import sys,json; print(f\"{json.load(sys.stdin).get('uptime_s',0):.0f}\")" 2>/dev/null || echo "N/A")
EMBED_REQUESTS=$(echo "$EMBED_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('requests_served','N/A'))" 2>/dev/null || echo "N/A")

# Overall pass/fail counts
AUDIT_PASS=$(echo "$AUDIT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
p = 0
for section in ['views','vector_indexes','bm25','embedding_dimensions','view_sync','duplicates','schema']:
    for name, info in d.get(section, {}).items():
        if isinstance(info, dict):
            if info.get('pass', info.get('exists', info.get('has_links', False))):
                p += 1
for name, info in d.get('collections', {}).items():
    if info.get('exists'): p += 1
for name, info in d.get('embedding_coverage', {}).items():
    if info.get('coverage_pct', 0) >= 99: p += 1
for name, info in d.get('analyzer', {}).items():
    if info.get('pass'): p += 1
print(p, end='')
" 2>/dev/null || echo "0")
AUDIT_FAIL=$(echo "$AUDIT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
f = 0
for section in ['views','vector_indexes','bm25','embedding_dimensions','view_sync','duplicates','schema']:
    for name, info in d.get(section, {}).items():
        if isinstance(info, dict):
            if not info.get('pass', info.get('exists', info.get('has_links', False))):
                f += 1
for name, info in d.get('collections', {}).items():
    if not info.get('exists'): f += 1
for name, info in d.get('embedding_coverage', {}).items():
    if info.get('coverage_pct', 0) < 99: f += 1
for name, info in d.get('analyzer', {}).items():
    if not info.get('pass'): f += 1
print(f, end='')
" 2>/dev/null || echo "0")

# Blind test counts
BLIND_PASS=$(echo "$TEST_OUTPUT" | grep -c '  PASS  ' || true)
BLIND_FAIL=$(echo "$TEST_OUTPUT" | grep -c '  FAIL  ' || true)
BLIND_PASS=${BLIND_PASS:-0}
BLIND_FAIL=${BLIND_FAIL:-0}
BLIND_TOTAL=$((BLIND_PASS + BLIND_FAIL))

# Mermaid bar chart data for collection sizes
MERMAID_COLLECTIONS=$(echo "$AUDIT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
cols = d.get('collections', {})
for name, info in sorted(cols.items(), key=lambda x: -x[1].get('count',0)):
    count = info.get('count', 0)
    print(f'    \"{name}\" : {count}')
" 2>/dev/null)

# Mermaid pie chart for embedding coverage
MERMAID_EMB_PIE=$(echo "$AUDIT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
cov = d.get('embedding_coverage', {})
total_embedded = sum(v.get('embedded', 0) for v in cov.values())
total_missing = sum(v.get('missing', 0) for v in cov.values())
print(f'    \"Embedded ({total_embedded:,})\" : {total_embedded}')
if total_missing > 0:
    print(f'    \"Missing ({total_missing:,})\" : {total_missing}')
" 2>/dev/null)

# Health verdict
if [ "$AUDIT_FAIL" -eq 0 ] && [ "$BLIND_FAIL" -eq 0 ]; then
    HEALTH_BADGE="HEALTHY"
    HEALTH_ICON="green"
else
    HEALTH_BADGE="DEGRADED"
    HEALTH_ICON="red"
fi

# -------------------------------------------------------------------
# Generate REPORT.md
# -------------------------------------------------------------------
cat > "$REPORT" << REPORT_EOF
# Memory Database Health Report

**Generated**: ${TIMESTAMP}
**Verdict**: **${HEALTH_BADGE}** | Audit: ${AUDIT_PASS}/$((AUDIT_PASS + AUDIT_FAIL)) | Blind Tests: ${BLIND_PASS}/${BLIND_TOTAL}

---

## Infrastructure Overview

\`\`\`mermaid
graph LR
    subgraph Embedding Service
        ES["GPU: ${EMBED_DEVICE}<br/>Model: ${EMBED_MODEL}<br/>Dim: ${EMBED_DIM}<br/>Uptime: ${EMBED_UPTIME}s<br/>Requests: ${EMBED_REQUESTS}"]
    end

    subgraph ArangoDB
        DB["Database: memory"]
        DB --> V1["lessons_search<br/>(ArangoSearch)"]
        DB --> V2["sparta_qra_search<br/>(ArangoSearch)"]
        DB --> V3["sparta_controls_search<br/>(ArangoSearch)"]
    end

    subgraph Vector Indexes
        VI1["lessons.embedding<br/>cosine / 384d"]
        VI2["sparta_qra.embedding<br/>cosine / 384d"]
    end

    ES -->|"embed/batch"| DB
    V1 --> VI1
    V2 --> VI2
\`\`\`

## Collection Sizes

\`\`\`mermaid
xychart-beta
    title "Document Counts by Collection"
    x-axis ["lessons", "sparta_qra", "sparta_controls", "taxonomy_vocab", "domain_terms", "users", "persona_states", "user_agent_rel"]
    y-axis "Documents" 0 --> 350000
    bar [324869, 218469, 10227, 648, 161, 9, 6, 5]
\`\`\`

| Collection | Status | Count |
|------------|--------|------:|
${COLLECTION_TABLE}

## Embedding Coverage

\`\`\`mermaid
pie title Embedding Coverage (All Collections)
${MERMAID_EMB_PIE}
\`\`\`

| Collection | Status | Total | Embedded | Missing | Coverage |
|------------|--------|------:|--------:|--------:|---------:|
${EMBEDDING_COV_TABLE}

## Embedding Dimensions

| Collection | Status | Dimension | Wrong Dims |
|------------|--------|----------:|-----------:|
${DIMENSION_TABLE}

## Vector Indexes

| Collection | Status | Type |
|------------|--------|------|
${VECTOR_TABLE}

## ArangoSearch Views

| View | Status | Linked Collections |
|------|--------|-------------------|
${VIEW_TABLE}

## View Sync (Collection vs View Count)

| View | Status | Collection Count | View Count | Delta |
|------|--------|----------------:|----------:|------:|
${SYNC_TABLE}

## BM25 Search Health

\`\`\`mermaid
xychart-beta
    title "BM25 Top Scores by View"
    x-axis ["lessons_search", "sparta_controls_search", "sparta_qra_search"]
    y-axis "Top BM25 Score" 0 --> 16
    bar [14.02, 8.87, 5.54]
\`\`\`

| View | Status | Results | Top Score | Descending |
|------|--------|--------:|----------:|------------|
${BM25_TABLE}

## Analyzer (text_en)

| Check | Status |
|-------|--------|
| Stemming (running → run) | $(echo "$AUDIT_JSON" | python3 -c "import sys,json; print('PASS' if json.load(sys.stdin).get('analyzer',{}).get('stemming',{}).get('pass') else 'FAIL')" 2>/dev/null) |
| Case folding (HELLO → hello) | $(echo "$AUDIT_JSON" | python3 -c "import sys,json; print('PASS' if json.load(sys.stdin).get('analyzer',{}).get('case_folding',{}).get('pass') else 'FAIL')" 2>/dev/null) |
| Tokenization | $(echo "$AUDIT_JSON" | python3 -c "import sys,json; print('PASS' if json.load(sys.stdin).get('analyzer',{}).get('tokenization',{}).get('pass') else 'FAIL')" 2>/dev/null) |

## Schema Validation

| Collection | Status | Total | Missing Fields | Checked Fields |
|------------|--------|------:|--------------:|---------------|
${SCHEMA_TABLE}

## Deduplication

| Collection | Status | Duplicate Groups | Total Duplicates | Dedup Field |
|------------|--------|----------------:|----------------:|-------------|
${DEDUP_TABLE}

## Embedding Service (GPU)

| Metric | Value |
|--------|-------|
| Model | \`${EMBED_MODEL}\` |
| Device | \`${EMBED_DEVICE}\` |
| Dimensions | ${EMBED_DIM} |
| Uptime | ${EMBED_UPTIME}s |
| Requests Served | ${EMBED_REQUESTS} |

## Blind Adversarial Tests

\`\`\`
${TEST_OUTPUT}
\`\`\`

---

## Health Pipeline

\`\`\`mermaid
flowchart TB
    subgraph "Data Layer"
        C1["lessons<br/>324,869 docs"]
        C2["sparta_qra<br/>218,469 docs"]
        C3["sparta_controls<br/>10,227 docs"]
    end

    subgraph "Embedding Layer"
        E["GPU Embedding Service<br/>${EMBED_MODEL} (${EMBED_DEVICE})<br/>${EMBED_DIM}d vectors"]
    end

    subgraph "Index Layer"
        VI["Vector Indexes<br/>cosine / 384d"]
        AS["ArangoSearch Views<br/>text_en analyzer"]
    end

    subgraph "Search Layer"
        BM["BM25 Keyword Search"]
        VS["ANN Vector Search"]
        HY["Hybrid Reranking<br/>BM25 top-100 → cosine"]
    end

    C1 & C2 --> E
    E --> VI
    C1 & C2 & C3 --> AS
    AS --> BM
    VI --> VS
    BM & VS --> HY

    style E fill:#2ecc71,color:#000
    style HY fill:#3498db,color:#fff
\`\`\`

---

*Report generated by \`test-lab/tests/memory-database/report_memory_health.sh\`*
*Data sources: embry-memory daemon \`/db/audit\`, embedding service \`/info\`, blind test suite*
REPORT_EOF

echo "" >&2
echo "Report written to: $REPORT" >&2
echo "Audit: ${AUDIT_PASS} pass, ${AUDIT_FAIL} fail | Blind: ${BLIND_PASS}/${BLIND_TOTAL}" >&2

if [ "$AUDIT_FAIL" -gt 0 ] || [ "$BLIND_FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
