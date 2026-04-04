## Control Extraction Pipeline (2026-02-25)

`/memory recall` now traverses **control extraction edges** connecting document chunks to framework controls (NIST, CWE, ATT&CK, SPARTA, D3FEND, ISO). This enables queries like "What does AC-2 mean for F-36 maintenance?" to return both the control definition AND the document paragraphs that reference it.

### Edge Collections

| Collection | Type | Count | Purpose |
|---|---|---|---|
| `chunk_control_edges` | Evidence | 86,552 | Document chunk references a control |
| `requirement_control_edges` | Claim | 40,210 | Requirement implements a control (`lean4_status` field) |
| `proof_requirement_edges` | Proof | (pending) | Lean4 formal verification of claims |

### How It Works in Recall

Two RecallSources use `extra_edge_collections` for automatic traversal:

- **`datalake_chunks`** source: traverses `chunk_control_edges` + `requirement_control_edges` → shows `referenced_controls` and `implements_controls` in results
- **`sparta_controls`** source: traverses both edge types in reverse → shows `referencing_chunks` and `implementing_requirements`

### 3-Tier Extraction Architecture

```
Document text → Tier 1 (Regex, wide net) → Tier 2 (RapidFuzz vs 7K control catalog) → Tier 3 (Classifier, future)
```

- **Tier 1**: Intentionally loose regex patterns (~80% recall, ~1ms/chunk)
- **Tier 2**: RapidFuzz validates candidates against `sparta_controls` catalog (exact + parent + fuzzy matching, threshold 85)
- **Tier 3**: Future trained classifier from Shadow-LEGO disagreements

### Requirement Detection

A chunk is a requirement (creates `requirement_control_edges` + `proof_jobs`) if ANY of:
- `asset_type` is Requirement, Table, or Equation
- Text contains SHALL/MUST/WILL (RFC 2119 modals)
- Has `req_id` from extractor s08
- Is a hardware data table (implicit requirement)

### Key Files

| File | Location | Purpose |
|---|---|---|
| `s12_framework_mapper.py` | extractor project | Pipeline step (runs after s10) |
| `backfill_chunk_control_edges.py` | memory/scripts/ | Batch backfill (2.2M chunks in 6.6 min) |
| `recall_sources.py` | graph_memory/lessons/ | RecallSource wiring with `extra_edge_collections` |
| `setup_schema.py` | graph_memory/ | Collections, indexes, ArangoSearch view |

---
