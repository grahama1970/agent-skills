---
name: best-practices-arangodb
description: >
  Repo-specific ArangoDB best practices: leverage text_en analyzer (stop words, stemming, BM25),
  use AQL functions (LEVENSHTEIN_DISTANCE, TOKENS, NGRAM_SIMILARITY, COSINE_SIMILARITY),
  store domain knowledge in collections not Python code, and never duplicate DB capabilities.
triggers:
  - best practices arangodb
  - arangodb conventions
  - arango search
  - bm25 search
  - stop words
  - stemming
  - levenshtein
  - fuzzy matching
  - domain terms
  - entity classification
  - aql query
license: MIT
metadata:
  database: ArangoDB
  client: python-arango
  defaults:
    database_name: memory
    analyzers: ["text_en", "identity"]
    search_pattern: BM25 + cosine rerank
    domain_collections: ["domain_terms", "taxonomy_vocabulary", "sparta_controls"]
    max_python_stopwords: 0
    max_hardcoded_domain_terms: 0
    performance_budgets:
      bm25_ms: 100
      hybrid_ms: 300
      entity_extraction_ms: 1000
      exact_lookup_ms: 10

taxonomy:
  - precision
  - resilience
provides:
  - best-practices-arangodb
  - skill-validation
composes:
  - best-practices-python
  - memory
  - ingest-code
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# ArangoDB Best Practices (Project Skill)

This skill codifies rules for using ArangoDB correctly in this repo. The core principle:

**ArangoDB's built-in features MUST be used instead of reimplementing them in Python.**

## The Anti-Pattern This Skill Prevents

Python code that duplicates what ArangoDB already does:
- Stop word lists in Python (ArangoDB `text_en` already strips them)
- Hand-rolled stemming in Python (ArangoDB `text_en` already stems via Snowball)
- Regex patterns that classify entity types (ArangoDB collections already know what things are)
- Hardcoded domain term lists (ArangoDB collections are the source of truth)
- Python-side BM25/TF-IDF scoring (ArangoDB `BM25()` does this server-side)
- Python-side cosine similarity loops (ArangoDB `COSINE_SIMILARITY()` does this server-side)

See [references/anti-patterns-duplicated-functionality.md](references/anti-patterns-duplicated-functionality.md) for 7 real removed-from-codebase examples.

## When to Apply

Use this skill whenever you:
- Write AQL queries or ArangoSearch code
- Add new collections or ArangoSearch views
- Work with entity extraction, intent mapping, or text search
- Add domain knowledge (terms, keywords, frameworks) to the system
- Implement fuzzy matching, spellcheck, or text classification

## Rules (priority order)

### 1. CRITICAL: No Stop Words in Python — `arango-no-python-stopwords`

ArangoDB's `text_en` analyzer already removes English stop words. NEVER maintain a stop word list in Python.

```python
# BAD — duplicates text_en analyzer
_STOPWORDS = frozenset({"the", "a", "an", "of", "for", "in", ...})

# GOOD — let ArangoDB handle it
cursor = db.aql.execute("RETURN TOKENS(@query, 'text_en')", bind_vars={"query": text})
```

### 2. CRITICAL: No Hand-Rolled Stemming — `arango-no-python-stemming`

ArangoDB's `text_en` uses Snowball stemming. NEVER strip suffixes in Python.

```python
# BAD
for suffix in ("s", "es", "ing", "ed", "ly"):
    if word.endswith(suffix): stem = word[:-len(suffix)]

# GOOD — ArangoDB stems automatically: "recommendations" matches "recommendation"
```

### 3. CRITICAL: Domain Knowledge in ArangoDB — `arango-no-hardcoded-domain-lists`

Domain terms, keywords, frameworks belong in ArangoDB collections, not Python dicts/frozensets.

Collections: `domain_terms`, `taxonomy_vocabulary`, `sparta_controls`.

### 4. CRITICAL: No Regex for Entity Classification — `arango-no-regex-classification`

Regex is for TOKENIZATION (finding candidates). Classification (what is it?) comes from ArangoDB.

**Exception**: `_extract_control_ids()` in trace.py uses regex to FIND ID-like patterns — that's tokenization, not classification.

### 5. HIGH: Use AQL Functions — `arango-use-aql-functions`

| Need | AQL Function | Python Anti-Pattern |
|------|-------------|-------------------|
| Fuzzy match | `LEVENSHTEIN_DISTANCE(a, b)` | `rapidfuzz` loop over all docs |
| Tokens | `TOKENS(@q, 'text_en')` | Python stop words + stemming |
| N-gram | `NGRAM_SIMILARITY(a, b, n)` | Hand-rolled comparison |
| BM25 | `BM25(doc)` | Python TF-IDF |
| Cosine | `COSINE_SIMILARITY(a, b)` | `numpy` dot product on all docs |

### 6. HIGH: Two-Stage BM25 + Cosine Rerank — `arango-two-stage-search`

NEVER brute-force scan all embeddings. BM25 top-100 → cosine rerank to top-k.

### 7. HIGH: One AQL Round-Trip — `arango-single-roundtrip`

NEVER split one server-side operation into two network round-trips.

### 8. MEDIUM: Batch Operations — `arango-batch-operations`

Use bulk AQL for large-scale operations (10K+ documents):

```aql
-- BAD: 222K individual UPDATE calls (3.3/s = 18 hours)
UPDATE {_key: @key} WITH {field: @val} IN collection

-- GOOD: Bulk update (50-100 docs per query)
FOR item IN @updates
  UPDATE {_key: item.key} WITH {field: item.val} IN collection
  RETURN 1
```

For batch exact matches, use one AQL with `FOR cid IN @cids` instead of N individual queries.

For HTTP endpoints with internal ThreadPoolExecutor, use batch endpoints (e.g., `/create-evidence-case-batch` with `max_workers: 32`).

### 9. MEDIUM: Identity Analyzer for Exact Matches — `arango-identity-for-exact`

Use `identity` (not `text_en`) for control IDs, framework names, categories.

### 10. MEDIUM: Database Name is Always "memory" — `arango-db-name-memory`

The only database is `memory`. `ARANGO_DB=lessons` anywhere = bug.

### 11. LOW: Cache Vocabulary Lookups — `arango-cache-vocab`

Module-level `_cache: T | None = None` + `_get_*()` function.

### 12. CRITICAL: BM25 Score > 0 Is NOT Grounding — `arango-bm25-not-grounding`

BM25 ALWAYS returns results for any security-adjacent query. A score > 0 does NOT prove a term exists. ID-like terms must be grounded via exact `control_id` match or fuzzy edit distance.

```python
# BAD — BM25 returns results for "X23-MUSTARD" because it matches "spoofing"
# GOOD — exact match: FOR c IN sparta_controls FILTER UPPER(c.control_id) == @cid
```

### 13. HIGH: Pre-Filter Before LEVENSHTEIN_DISTANCE — `arango-prefilter-fuzzy`

Full table scan = 268ms. Length ±3 + prefix overlap pre-filter = 4ms.

```aql
-- GOOD — pre-filter reduces 9,337 → 61 candidates
FOR c IN sparta_controls
    LET cid = UPPER(c.control_id)
    FILTER LENGTH(cid) >= LENGTH(@candidate) - 3 AND LENGTH(cid) <= LENGTH(@candidate) + 3
    FILTER LEFT(cid, 1) == LEFT(@candidate, 1) OR CONTAINS(cid, LEFT(@candidate, 2))
    LET dist = LEVENSHTEIN_DISTANCE(cid, @candidate)
    FILTER dist <= 2
    SORT dist LIMIT 3
    RETURN {control_id: c.control_id, distance: dist}
```

### 14. HIGH: Concurrent Queries — `arango-concurrent-queries`

ArangoDB is multi-threaded. Use `ThreadPoolExecutor` for independent queries.

```python
with ThreadPoolExecutor(max_workers=3) as pool:
    f1 = pool.submit(lambda: list(db.aql.execute("...")))
    f2 = pool.submit(lambda: list(db.aql.execute("...")))
    results1, results2 = f1.result(), f2.result()
```

### 15. HIGH: Performance Budgets — `arango-performance-budgets`

| Operation | Budget |
|-----------|--------|
| BM25 text search | <100ms |
| Hybrid search (BM25 + cosine) | <300ms |
| Entity extraction (full pipeline) | <1s |
| Exact lookup by indexed field | <10ms |

Use `tests/test_memory_performance.py` to validate.

### 16. MEDIUM: No DOCUMENT() in AQL Loops — `arango-no-document-in-loops`

```aql
-- BAD: DOCUMENT('lessons', key) in a loop
-- GOOD: FOR l IN lessons FILTER l._key == key LIMIT 1
```

### 17. CRITICAL: Always Hybrid Search — `arango-always-hybrid-search`

Every retrieval query MUST use BM25 + semantic embedding + multi-hop graph traversal. NEVER use a single lane alone.

```python
# GOOD — via RecallSources
from graph_memory.hybrid_search import hybrid_search_sparta_qra
results = hybrid_search_sparta_qra(query, db, embedding_service, k=12)
```

Direct single-lane queries only in unit tests and diagnostics.

### 18. CRITICAL: No Silent Fallback — `arango-no-silent-fallback`

When a search lane fails, the code MUST:
1. **Log at `logger.error`** (NOT `logger.debug`) with exception context
2. **Signal degradation** in the result so the caller knows
3. **NEVER** silently return partial results as if complete
4. **NEVER** use bare `except Exception:` — always capture as `except Exception as exc:`

`logger.debug` in exception handlers is a silent fallback — invisible in production.
This rule applies to ALL AQL queries, view searches, and collection operations.

### 18b. CRITICAL: Every Collection Searchable via /recall — `arango-recall-all-collections`

Every document collection with an ArangoSearch view MUST be searchable via `/recall`.
Use scope routing to filter (e.g., `scope=sparta` → only `sparta_*` collections).
New collections MUST be added to both the ArangoSearch view AND `bm25_rank()`.
`/recall` MUST return BM25 + semantic (cosine) + multi-hop graph traversal for ALL collections.

### 18c. CRITICAL: Use @@coll bind variables — `arango-no-collection-interpolation`

Collection names in AQL MUST use `@@coll` bind variables, NOT f-string interpolation.
```python
# WRONG — AQL injection risk
aql = f"FOR d IN {collection} FILTER d._key == @key RETURN d"

# RIGHT — bind variable for collection
aql = "FOR d IN @@coll FILTER d._key == @key RETURN d"
db.aql.execute(aql, bind_vars={"@coll": collection, "key": key})
```

### 19. MEDIUM: Cache Errors Must Log — `arango-cache-must-log`

DB-backed cache `except` blocks MUST log at `logger.error`. Cross-ref: `/best-practices-python` rule `correctness-no-silent-fallback`.

### 20. HIGH: No Null Filters for Backfills — `arango-no-null-backfill`

NEVER use `FILTER doc.field == null` for batch backfill operations on large collections.

**Why it fails:** As documents get updated, fewer match `field == null`. Without an index on the field, ArangoDB scans progressively more documents to find fewer matches. Rate degrades from 20/s → 7/s → worse.

```aql
-- BAD — progressively slower as nulls decrease (no index helps)
FOR doc IN sparta_qra
    FILTER doc.lineage == null
    FILTER doc._key > @last_key
    LIMIT 200
    RETURN doc

-- GOOD — version-based, indexable, constant performance
FOR doc IN sparta_qra
    FILTER doc.lineage.graph_version < @target_version OR doc.lineage == null
    FILTER doc._key > @last_key
    LIMIT 200
    RETURN doc
```

**Pattern:**
1. Add a version field (e.g., `lineage.graph_version`)
2. Create persistent index: `db.sparta_qra.ensureIndex({type: "persistent", fields: ["lineage.graph_version"]})`
3. Query by version, not null
4. Bump version constant when schema changes

**Real incident (2026-04-13):** 171K QRA lineage backfill started at 20/s, degraded to 7/s by 50% completion. Root cause: unindexed `lineage == null` filter.

### 21. HIGH: Sparse Vector Index UPDATE Bug — `arango-vector-update-bug`

ArangoDB versions < 3.12.9 have a bug where sparse vector indexes block UPDATE operations on documents that don't have the vector field, even though `sparse: true` should allow this.

**Error:** `[HTTP 400][ERR 10] vector field not present in document <key>`

**GitHub Issue:** [arangodb/arangodb#22568](https://github.com/arangodb/arangodb/issues/22568)

```python
# BAD — fails on docs without embedding (versions < 3.12.9)
db.aql.execute("UPDATE {_key: @key} WITH {lineage: @lin} IN sparta_qra", ...)

# WORKAROUND — drop index, update, recreate
coll = db.collection('sparta_qra')
idx_config = next(i for i in coll.indexes() if i['type'] == 'vector')
coll.delete_index(idx_config['id'])

# ... do all updates ...

coll.add_index({
    'type': 'vector',
    'name': idx_config['name'],
    'fields': idx_config['fields'],
    'params': idx_config['params'],
    'sparse': True,
    'inBackground': True
})
```

**When to apply:** Any batch update to a collection with a sparse vector index where some docs lack the vector field.

**Real incident (2026-04-14):** Lineage backfill failed on 269 docs without embeddings. Error message was misleading ("vector field not present") even when providing the embedding in the UPDATE — the index validates against the OLD document state.

### 22. CRITICAL: All Searchable Docs Must Have Embeddings — `arango-require-embeddings`

Every document in a searchable collection (sparta_qra, lessons, sparta_url_knowledge) MUST have an `embedding` field with a 384-dimension vector. Docs without embeddings:
1. Break the dense lane of hybrid search (cosine similarity returns 0)
2. Trigger sparse vector index bugs on UPDATE operations
3. Create data quality gaps that degrade recall

```python
# BAD — writing doc without embedding
db.aql.execute("INSERT {question: @q, answer: @a} INTO sparta_qra", ...)

# GOOD — always include embedding
embedding = embedding_service.embed(question)  # 384-dim vector
db.aql.execute("INSERT {question: @q, answer: @a, embedding: @emb} INTO sparta_qra",
    bind_vars={"q": question, "a": answer, "emb": embedding})
```

**Monitoring:**
```aql
-- Count docs missing embeddings (should be 0)
FOR d IN sparta_qra
  FILTER !HAS(d, "embedding") OR d.embedding == null
  COLLECT WITH COUNT INTO cnt
  RETURN cnt
```

**Backfill script:** Use `/ops-arango embeddings --fix` to populate missing embeddings.

**Real incident (2026-04-16):** 2,937 QRAs missing embeddings discovered during batch update. These were created by a script that skipped the embedding step.

## Enforcement

- **PostToolUse hook** `no-regex-silo.sh` fires on every Edit/Write to .py files
- Catches: frozensets >10 entries, regex entity classifiers, stopword lists >50, hand-rolled stemming, files >800 lines
- Exit code 2 = hard block with explanation

## ArangoDB Features Reference

| Feature | AQL Syntax | Purpose |
|---------|-----------|---------|
| Stop word removal | `TOKENS(@q, 'text_en')` | Returns only content words |
| Snowball stemming | `TOKENS(@q, 'text_en')` | "running" -> "run" |
| BM25 scoring | `BM25(doc)` | TF-IDF with length normalization |
| Exact match | `ANALYZER(doc.field == @val, 'identity')` | No stemming/stop words |
| Fuzzy match | `LEVENSHTEIN_DISTANCE(a, b)` | Edit distance between strings |
| N-gram similarity | `NGRAM_SIMILARITY(a, b, n)` | Character n-gram overlap |
| Cosine similarity | `COSINE_SIMILARITY(a, b)` | Vector distance (no ANN index) |
| Token search | `SEARCH ANALYZER(doc.f IN TOKENS(@q, 'text_en'), 'text_en')` | Full-text search |

## Key Collections

| Collection | Purpose | Key Fields |
|-----------|---------|------------|
| `sparta_controls` | All controls (4,253) | `control_id`, `name`, `source_framework`, `description` |
| `sparta_qra` | QRA corpus (90K+) | `question`, `answer`, `control_id`, `reasoning` |
| `domain_terms` | Known non-control terms | `term`, `category` |
| `taxonomy_vocabulary` | Bridge/tactical keywords | `term`, `vocabulary_type`, `bridge_concept`, `category` |
| `lessons` | Memory lessons | `problem`, `solution`, `tags` |

## Querying ArangoDB Documentation

The full ArangoDB docs-hugo documentation is ingested into `/memory` via `/ingest-code`.

```bash
# Query ArangoDB docs — same as any /memory recall
/memory recall --q "AQL BM25 scoring ArangoSearch"
/memory recall --q "graph traversal OUTBOUND depth"
/memory recall --q "text_en analyzer stop words stemming"

# First-time ingestion (or manual re-ingest)
./run.sh ingest

# Nightly incremental update (wired into /monitor-memory)
./run.sh update

# Check cache state
./run.sh status
```

Docs are stored with scope `arangodb-docs` and cached on 12TB at `/mnt/storage12tb/cache/arangodb-docs-hugo`.

## References (detailed content)

- [references/cookbook-views.md](references/cookbook-views.md) — ArangoSearch view creation patterns
- [references/cookbook-aql-patterns.md](references/cookbook-aql-patterns.md) — AQL recipes (UPSERT, traversal, BM25, batch)
- [references/cookbook-debugging.md](references/cookbook-debugging.md) — Debugging AQL (explain, profile, check views)
- [references/anti-patterns-duplicated-functionality.md](references/anti-patterns-duplicated-functionality.md) — 7 real removed anti-patterns with fixes
