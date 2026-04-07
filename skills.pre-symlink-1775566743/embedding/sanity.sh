#!/usr/bin/env bash
#
# Sanity check for embedding skill — verifies both backends and ArangoDB contract
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ERRORS=0

pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; ERRORS=$((ERRORS + 1)); }

echo "=== Embedding Skill Sanity Check ==="

# 1. Text backend (MiniLM, 384d)
echo ""
echo "1. Text backend (:8602)..."
if result=$("$SCRIPT_DIR/run.sh" embed --text "sanity check" 2>/dev/null); then
    dims=$(echo "$result" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['embedding']))" 2>/dev/null)
    if [ "$dims" = "384" ]; then
        pass "MiniLM: ${dims}d embedding"
    else
        fail "MiniLM: expected 384d, got ${dims}d"
    fi
else
    fail "Text backend unreachable"
fi

# 2. Multimodal backend (vLLM, 2048d) — optional, may not be running
echo ""
echo "2. Multimodal backend (:8603)..."
if curl -s http://127.0.0.1:8603/health >/dev/null 2>&1; then
    mm_result=$(curl -s http://127.0.0.1:8603/v1/embeddings \
        -H "Content-Type: application/json" \
        -d '{"model":"Qwen/Qwen3-VL-Embedding-2B","input":"sanity check","encoding_format":"float"}' 2>/dev/null)
    mm_dims=$(echo "$mm_result" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['data'][0]['embedding']))" 2>/dev/null)
    if [ "$mm_dims" = "2048" ]; then
        pass "Qwen3-VL: ${mm_dims}d embedding"
    else
        fail "Qwen3-VL: expected 2048d, got ${mm_dims}d"
    fi
else
    echo "  - Multimodal backend not running (optional)"
fi

# 3. Memory daemon connectivity
echo ""
echo "3. Memory daemon..."
if python3 -c "
import httpx
transport = httpx.HTTPTransport(uds='/run/user/1000/embry/memory.sock')
client = httpx.Client(transport=transport, base_url='http://localhost', timeout=5.0)
r = client.get('/health')
r.raise_for_status()
print('OK')
" 2>/dev/null | grep -q "OK"; then
    pass "Memory daemon reachable"
else
    fail "Memory daemon unreachable"
fi

# 4. ArangoDB embedding coverage
echo ""
echo "4. Embedding coverage..."
python3 -c "
import httpx

transport = httpx.HTTPTransport(uds='/run/user/1000/embry/memory.sock')
client = httpx.Client(transport=transport, base_url='http://localhost', timeout=30.0)

collections = {
    'datalake_chunks': ['embedding', 'embedding_visual'],
    'lessons': ['embedding'],
    'sparta_qra': ['embedding'],
}

for coll, fields in collections.items():
    r = client.post('/list', json={'collection': coll, 'limit': 1})
    total = r.json()['total']
    for field in fields:
        r2 = client.post('/list', json={'collection': coll, 'filters': {field: None}, 'limit': 1})
        missing = r2.json()['total']
        has = total - missing
        pct = has / total * 100 if total > 0 else 0
        dims = '2048d' if 'visual' in field else '384d'
        status = 'OK' if pct > 80 else 'LOW' if pct > 0 else 'NONE'
        print(f'  {coll}.{field} ({dims}): {has:,}/{total:,} ({pct:.1f}%) [{status}]')
" 2>/dev/null || fail "Coverage check failed"

# 5. Vector index verification (ANN search)
echo ""
echo "5. Vector index ANN search..."
python3 -c "
import httpx, sys

transport = httpx.HTTPTransport(uds='/run/user/1000/embry/memory.sock')
client = httpx.Client(transport=transport, base_url='http://localhost', timeout=30.0)

# Get a real embedding to use as query vector
r = client.post('/list', json={
    'collection': 'datalake_chunks',
    'limit': 1,
    'return_fields': ['_key', 'embedding', 'embedding_visual'],
})
doc = r.json()['documents'][0]

# Test 384d ANN
if doc.get('embedding'):
    r2 = client.post('/recall', json={'q': 'test query', 'k': 1, 'collections': ['datalake_chunks']})
    if r2.json().get('items'):
        print('  ANN 384d (embedding): OK')
    else:
        print('  ANN 384d (embedding): NO RESULTS')

# Test 2048d ANN — use /list to verify the field exists and has data
r3 = client.post('/list', json={
    'collection': 'datalake_chunks',
    'limit': 1,
    'filters': {'asset_type': 'Table'},
    'return_fields': ['_key', 'embedding_visual'],
})
if r3.json()['documents'] and r3.json()['documents'][0].get('embedding_visual'):
    vec = r3.json()['documents'][0]['embedding_visual']
    print(f'  embedding_visual sample: {len(vec)}d vector present')
else:
    print('  embedding_visual: no data found')
" 2>/dev/null || fail "ANN search check failed"

# Summary
echo ""
if [ $ERRORS -eq 0 ]; then
    echo "=== SANITY CHECK PASSED ==="
    exit 0
else
    echo "=== SANITY CHECK FAILED ($ERRORS errors) ==="
    exit 1
fi
