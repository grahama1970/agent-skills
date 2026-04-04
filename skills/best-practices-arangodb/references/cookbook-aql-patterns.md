# Cookbook: AQL Patterns (Good vs Bad)

## UPSERT (dedup on insert)

```aql
-- GOOD — atomic upsert with dedup key
UPSERT { problem_hash: @hash, scope: @scope }
INSERT @doc
UPDATE @doc
IN lessons
RETURN NEW

-- BAD — check-then-insert race condition
LET exists = FIRST(FOR l IN lessons FILTER l.problem_hash == @hash RETURN 1)
FILTER exists == null
INSERT @doc INTO lessons
```

## Graph Traversal (multi-hop)

```aql
-- Find related lessons within 2 hops
FOR v, e, p IN 1..2 OUTBOUND @start_id lesson_edges
    OPTIONS {uniqueVertices: "global", bfs: true}
    FILTER v.scope == @scope OR @scope == ""
    RETURN DISTINCT {
        _key: v._key,
        title: v.title,
        relation: e.relation_type,
        depth: LENGTH(p.edges)
    }
```

```python
# Python — always use bind variables, never string interpolation
results = list(db.aql.execute("""
    FOR v, e IN 1..2 OUTBOUND @start lesson_edges
        OPTIONS {uniqueVertices: "global", bfs: true}
        RETURN {_key: v._key, title: v.title, relation: e.relation_type}
""", bind_vars={"start": f"lessons/{lesson_key}"}))
```

## BM25 Full-Text Search with Scoring

```aql
-- GOOD — BM25 search with score in output
FOR doc IN lessons_search
    SEARCH ANALYZER(doc.problem IN TOKENS(@query, 'text_en'), 'text_en')
    SORT BM25(doc) DESC
    LIMIT @k
    RETURN MERGE(doc, {_score: BM25(doc)})
```

## Batch Existence Check

```aql
-- GOOD — check which control IDs exist in one query
FOR cid IN @candidate_ids
    LET ctrl = FIRST(
        FOR c IN sparta_controls
            FILTER UPPER(c.control_id) == UPPER(cid)
            LIMIT 1
            RETURN c
    )
    RETURN {
        candidate: cid,
        exists: ctrl != null,
        control_id: ctrl.control_id,
        name: ctrl.name,
        framework: ctrl.source_framework
    }
```

## Conditional Update (tag stamping)

```aql
-- GOOD — update specific fields without replacing entire doc
FOR l IN lessons
    FILTER l._key == @key
    UPDATE l WITH {
        bridge_attributes: @bridges,
        taxonomy_method: "sweep-keyword",
        taxonomy_updated_at: DATE_NOW()
    } IN lessons
    RETURN NEW
```

## Bind Variable Syntax

```python
# BAD — string interpolation (SQL injection risk + breaks on quotes)
query = f"FOR l IN lessons FILTER l.title == '{user_input}' RETURN l"

# GOOD — bind variables (safe + fast due to query plan caching)
query = "FOR l IN lessons FILTER l.title == @title RETURN l"
cursor = db.aql.execute(query, bind_vars={"title": user_input})

# BAD — collection name in bind vars (must use @@coll syntax)
db.aql.execute("INSERT @doc INTO @coll", bind_vars={"doc": doc, "coll": "lessons"})

# GOOD — @@ prefix for collection names
db.aql.execute("INSERT @doc INTO @@coll", bind_vars={"doc": doc, "@coll": "lessons"})
```
