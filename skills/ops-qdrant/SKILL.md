---
name: ops-qdrant
description: >
  Read-only Qdrant vector-store health detector. Lists collections, flags
  expected-but-missing collections, reports per-collection point counts, and
  probes end-to-end semantic recall through the memory daemon (dense score).
  Detection only — it performs NO writes. All Qdrant mutation and semantic sync
  stay in the memory repo per the memory contract. Use for "qdrant health",
  "check qdrant collections", "dense recall is zero", "vector store health",
  "ops-qdrant".
triggers:
  - qdrant health
  - check qdrant collections
  - qdrant collection missing
  - dense recall zero
  - vector store health
  - semantic recall broken
  - is the vector database healthy
  - how many vectors are stored
  - how many points in qdrant
  - what embeddings does qdrant have
  - which collections have text and image embeddings
  - how big is the vector store
  - ops qdrant
allowed-tools: Bash
runtime_self_improvement: basic
metadata:
  short-description: Read-only Qdrant health and semantic-recall detection
provides:
  - ops-qdrant
  - vector-store-health
composes:
  - memory
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - observability
  - resilience
  - memory-knowledge
disciplines:
  - observability-operations
  - memory-knowledge
---

# ops-qdrant

Read-only health detection for the Qdrant vector store and the semantic-recall
path that depends on it. It answers three questions without mutating anything:

1. Is Qdrant up, and which collections exist?
2. Do the collections we expect exist, and how many points does each hold?
3. Does end-to-end **dense** (semantic) recall actually work through the memory
   daemon, or has it silently degraded to BM25-only (`dense == 0.0`)?

## Boundary (non-negotiable)

This skill NEVER writes to Qdrant or Arango. Per `memory/SKILL.md`, all AQL and
all Qdrant mutation/sync logic live ONLY in `~/workspace/experiments/memory`.
ops-qdrant detects and reports; remediation is triggered by `ops-memory` calling
the memory repo's sanctioned migration (`migrate_arango_embeddings_to_qdrant.py`)
and daemon endpoints. If you find a gap here, do not "fix" it from this skill.

## Commands

```bash
# Full read-only health report (human-readable)
./run.sh check

# Same as JSON for monitors / ops-memory composition
./run.sh check --json

# Just list collections + point counts
./run.sh collections

# Just the end-to-end dense-recall probe through the daemon
./run.sh dense-probe --q "memory first recall pattern"

# Flag expected collections that are absent (comma-separated, or via env)
./run.sh check --expect memory_chunks_mm_jina_v5_omni_small_1024,persona_memory
```

## Environment

| Var | Default | Meaning |
|-----|---------|---------|
| `QDRANT_URL` | `http://127.0.0.1:6333` | Qdrant REST endpoint |
| `MEMORY_URL` | `http://127.0.0.1:8601` | memory daemon (owns `/recall`) |
| `EMBED_URL` | `http://127.0.0.1:8603` | published jina embedder health |
| `OPS_QDRANT_EXPECT` | (unset) | comma-separated collections that must exist |

## Signals

- `qdrant_up=false` → hard failure; Qdrant unreachable. Exit 2.
- `missing_expected` non-empty → an expected collection is absent from Qdrant.
- `dense_max == 0.0` with `found=true` → **semantic recall degraded to BM25-only**
  (the `graph-memory-operator#145` condition). Per `memory/SKILL.md`, `dense=0.0`
  means Qdrant semantic recall is unavailable — check `embry-embedding-mm`,
  `embry-qdrant`, and `qdrant_point_id` metadata.
- `embedder_up=false` → the daemon cannot compute query vectors.

## JSON shape

```json
{
  "schema": "ops_qdrant.health.v1",
  "qdrant_up": true,
  "embedder_up": true,
  "memory_daemon_up": true,
  "collections": [{"name": "...", "points": 12345}],
  "missing_expected": ["skill_chains"],
  "dense_probe": {"q": "...", "found": true, "dense_max": 0.0, "dense_ok": false},
  "status": "degraded",
  "warnings": ["dense recall is 0.0 (BM25-only); Qdrant semantic recall unavailable"]
}
```

`status` is `healthy`, `degraded`, or `down`. Exit code: 0 healthy/degraded
(report written), 2 when Qdrant itself is unreachable.

## References (retrieve on demand — do not vendor)

External docs drift; cite the canonical URLs and fetch them when needed with
`/context7` (library docs) or `/fetcher` (any URL/PDF) rather than caching stale
copies. All four were reachable (HTTP 200) as of 2026-08-24.

- Qdrant docs (concepts, collections, vectors): <https://qdrant.tech/documentation/>
- Qdrant collection-info API (points_count, named vectors): <https://api.qdrant.tech/api-reference/collections/get-collection>
- jina-embeddings-v4 model card: <https://jina.ai/models/jina-embeddings-v4/>
- jina-embeddings-v4 on Hugging Face: <https://huggingface.co/jinaai/jina-embeddings-v4>
- jina-embeddings-v4 paper (unified text+image, single/multi-vector): <https://arxiv.org/abs/2506.18902>

Retrieval examples:

```bash
# Library-doc lookup for Qdrant API shapes
skills/context7/run.sh "qdrant collection info named vectors points_count"
# Fetch a specific page/PDF for offline reading in this turn
skills/fetcher/run.sh "https://api.qdrant.tech/api-reference/collections/get-collection"
```

