# Hybrid RAG+QRA Retrieval Assessment for /ask

## Executive Summary

The current `/ask` skill uses single-mode retrieval (`memory recall`), which already combines semantic search + BM25 + multi-hop graph traversal internally. However, it does **not** explicitly leverage the different memory collections for hybrid retrieval:

- **QRA pairs** (`lessons` collection) - structured Question-Reasoning-Answer pairs
- **Raw chunks** (`doc_chunks` collection) - traditional RAG document chunks
- **Episodic context** (`agent_conversations`) - prior agent interactions

## Current State

```
ask.py:ask()
    │
    ├── run_memory_recall(question, scope, k)  ← Single query, all collections
    │
    └── (optional) bridge_traversal            ← Multi-hop via taxonomy bridges
```

**Issues:**
1. No collection-specific weighting (QRA pairs vs raw chunks)
2. No explicit "reasoning" extraction from QRA format
3. Bridge tags from learn.py not used for recall filtering

## Proposed Hybrid Architecture

```
ask.py:ask_hybrid()
    │
    ├── Phase 1: QRA Recall
    │   └── recall --q query --collections lessons --tags bridge:* --k 5
    │   └── Parse structured problem/solution pairs
    │
    ├── Phase 2: RAG Recall
    │   └── recall --q query --collections doc_chunks --k 3
    │   └── Parse raw text chunks
    │
    ├── Phase 3: Episodic Recall (optional)
    │   └── recall --q query --collections agent_conversations --k 2
    │   └── Parse prior agent turns for context
    │
    ├── Phase 4: Residue Integration
    │   └── residue --limit 3
    │   └── Get temporal memory (dream lag, day residue)
    │
    └── Phase 5: Synthesis
        └── Deduplicate, rank, synthesize answer
        └── Prefer QRA pairs (structured) over raw chunks
        └── Include reasoning from QRA pairs in response
```

## Memory Collections Available

| Collection | Type | Use Case | Priority |
|------------|------|----------|----------|
| `lessons` | QRA | Extracted Q-R-A pairs from learning | High |
| `doc_chunks` | RAG | Raw documentation chunks | Medium |
| `lesson_texts` | Full-text | Detailed problem/solution content | Medium |
| `agent_conversations` | Episodic | Prior agent interactions | Low |

## Implementation Plan

### Step 1: Add Collection-Specific Queries

```python
def ask_hybrid(question, scope, k=5, use_bridges=False):
    # QRA recall (structured)
    qra_result = run_memory_recall(
        question, scope, k=5,
        collections="lessons",
        tags=["bridge:*"] if use_bridges else None
    )

    # RAG recall (raw chunks)
    rag_result = run_memory_recall(
        question, scope, k=3,
        collections="doc_chunks"
    )

    # Combine with QRA priority
    items = merge_results(qra_result, rag_result, qra_weight=0.7)
```

### Step 2: Update run_memory_recall

```python
def run_memory_recall(query, scope, k=5, collections=None, tags=None, timeout=15):
    args = ["recall", "-q", query, "--scope", scope, "--k", str(k)]

    if collections:
        args.extend(["--collections", collections])

    if tags:
        for tag in tags:
            args.extend(["--tags", tag])

    # ... rest of implementation
```

### Step 3: Add Reasoning Extraction

QRA pairs have a specific format. Extract the "Reasoning" part:

```python
def extract_reasoning(qra_item):
    """Extract reasoning from QRA-formatted solution."""
    solution = qra_item.get("solution", "")

    # Look for reasoning markers
    if "Reasoning:" in solution:
        reasoning = solution.split("Reasoning:")[1].split("Answer:")[0]
        return reasoning.strip()

    return None
```

### Step 4: Weighted Merge

```python
def merge_results(qra_items, rag_items, qra_weight=0.7):
    """Merge QRA and RAG results with QRA preference."""
    merged = []
    seen = set()

    # Add QRA items first with higher weight
    for item in qra_items:
        key = item.get("problem", "")[:100]
        if key not in seen:
            item["source_type"] = "qra"
            item["weight"] = qra_weight
            merged.append(item)
            seen.add(key)

    # Add RAG items with lower weight
    for item in rag_items:
        key = item.get("problem", "")[:100]
        if key not in seen:
            item["source_type"] = "rag"
            item["weight"] = 1.0 - qra_weight
            merged.append(item)
            seen.add(key)

    return sorted(merged, key=lambda x: -x.get("weight", 0.5))
```

## Verification

1. Query with known QRA content should return structured pairs first
2. Query with only raw doc content should still work via RAG fallback
3. Bridge tags from learning should improve recall precision
4. Response should include reasoning when available

## Complexity Assessment

| Component | Effort | Risk |
|-----------|--------|------|
| run_memory_recall updates | Low | Low |
| Collection-specific queries | Low | Low |
| Result merging | Medium | Low |
| Reasoning extraction | Low | Low |
| Integration testing | Medium | Medium |

**Total Estimate:** 2-3 hours of focused development

## Recommendation

**Proceed with implementation.** The hybrid approach:

1. Preserves existing functionality (single-mode recall still works)
2. Adds structured QRA retrieval for better reasoning
3. Uses bridge tags from learn.py for precision
4. Gracefully degrades if specific collections are empty

## Next Steps

1. [ ] Update `run_memory_recall()` to accept `collections` and `tags` parameters
2. [ ] Add `ask_hybrid()` function alongside existing `ask()`
3. [ ] Add `--hybrid` flag to CLI
4. [ ] Add reasoning extraction for QRA pairs
5. [ ] Test with behavioral scope (Sapolsky/Barrett personas)
