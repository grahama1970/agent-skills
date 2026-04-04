# Cookbook: Debugging AQL

## 1. Explain Query Plan

```python
# See what indexes/views the query will use
plan = db.aql.explain("""
    FOR doc IN lessons_search
        SEARCH ANALYZER(doc.problem IN TOKENS(@query, 'text_en'), 'text_en')
        SORT BM25(doc) DESC LIMIT 10
        RETURN doc
""", bind_vars={"query": "satellite jamming"})
print(plan)  # Shows: EnumerateViewNode → uses ArangoSearch index
```

## 2. Profile Query Execution

```python
# Get execution stats (time, scanned, filtered)
import time
t0 = time.perf_counter()
cursor = db.aql.execute(
    "FOR doc IN lessons_search SEARCH ... RETURN doc",
    bind_vars={"query": "test"},
    full_count=True,  # get total matching count
)
results = list(cursor)
elapsed = (time.perf_counter() - t0) * 1000
print(f"{elapsed:.1f}ms, {len(results)} results, full_count={cursor.statistics().get('fullCount')}")
```

## 3. Check View State

```python
# Verify view exists and has expected links
views = {v["name"]: v for v in db.views()}
view = views.get("lessons_search")
if view:
    props = db.view("lessons_search").get("properties", {})
    print(f"Links: {list(props.get('links', {}).keys())}")
else:
    print("VIEW MISSING — run setup_schema.ensure_collections_and_view()")
```

## 4. Test Analyzer Tokenization

```python
# See exactly what tokens text_en produces
tokens = list(db.aql.execute(
    "RETURN TOKENS(@text, 'text_en')",
    bind_vars={"text": "How do satellite systems protect against RF jamming attacks?"}
))[0]
print(tokens)
# → ['how', 'do', 'satellit', 'system', 'protect', 'against', 'rf', 'jam', 'attack']
# Note: "satellite" → "satellit", "jamming" → "jam", "systems" → "system"
```

## 5. Verify Collection Exists

```python
from graph_memory.arango_client import get_db
db = get_db()

# Check collection
if db.has_collection("my_collection"):
    count = db.collection("my_collection").count()
    print(f"my_collection: {count} documents")
else:
    print("MISSING — run setup_schema.ensure_collections_and_view()")
```

## 6. Quick Diagnostic

```python
# Verify text_en analyzer works
tokens = list(db.aql.execute("RETURN TOKENS('How does the satellite protect against attacks', 'text_en')"))[0]
print(tokens)  # ['how', 'doe', 'satellit', 'protect', 'against', 'attack'] — stemmed, some stops removed
```
