---
name: ops-memory
description: >
  Natural-language front door that de-opaques the /memory stack — ArangoDB +
  Qdrant + the jina embedder + the memory daemon. Merges health, renders the
  topology as an ASCII chart, and prints a per-collection metrics matrix that
  flags collections which went stale, lost their Qdrant vector sync, hold no
  secondary index, are empty, or violate the "Arango stores no embedding
  arrays" contract. Also lists and triggers ArangoDB backups on the 12TB drive.
  Detection and read-only backups only — all Arango/Qdrant mutation and semantic
  sync stay in the memory repo. Use for "is the memory database healthy",
  "how does /memory work", "which collections aren't vector-synced", "show me
  stale collections", "how many embeddings are stored", "backup arangodb",
  "memory health", "ops-memory".
triggers:
  - is the database healthy
  - memory health
  - is memory working
  - how does /memory work
  - show me the memory architecture
  - how is the database constructed
  - what is the memory schema
  - how many embeddings are stored
  - how many vectors are stored
  - which collections are not vector synced
  - which collections are missing embeddings
  - show me stale collections
  - which collections have no index
  - are the arango backups current
  - backup the memory database
  - fix semantic recall
  - ops memory
allowed-tools: Bash
runtime_self_improvement: basic
metadata:
  short-description: Front door + health/metrics/topology/backups for the /memory stack
provides:
  - memory-stack-health
  - memory-stack-metrics
  - memory-stack-topology
composes:
  - ops-arango
  - ops-qdrant
  - memory
  - phart-dag-chart
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-arangodb
taxonomy:
  - observability
  - resilience
  - memory-knowledge
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY COMMAND.

# ops-memory

The memory/database setup is no longer opaque. `ops-memory` is the one place to
ask "is /memory healthy, how is it built, and what is quietly rotting?" — and to
take a backup. It **composes the owning skills**; it never touches ArangoDB or
Qdrant directly.

## Boundary (non-negotiable)

- **No direct DB access.** ops-memory shells out to `ops-arango` (Arango admin +
  read-only `coverage`), `ops-qdrant` (read-only vector health), and `memory`
  (`/recall`). It has no `arango`/`qdrant` client and no `httpx` of its own.
- **Detection + read-only backups only.** `backup --now` and `fix --apply` are
  the only side effects, and both are explicit, gated subcommands.
- **Semantic-sync repair is memory-repo work.** `fix` triggers the sanctioned
  `migrate_arango_embeddings_to_qdrant.py`; it never reimplements sync.
- All child calls use argument lists (never `shell=True`); every child payload
  is validated by a typed dataclass seam (`ArangoCheck`, `ArangoCoverage`,
  `QdrantHealth`) and drift raises `SeamViolation` (fail closed).

## Command surface

```
ops-memory health [--json]                  # merged ArangoDB + Qdrant health
ops-memory metrics [--json] [--sample N] [--stale-days D]
                                            # per-collection matrix + flags
ops-memory topology [--chart] [--json]      # stack wiring; --chart via phart-dag-chart
ops-memory explain "<question>"             # NL router over the above
ops-memory recall "<query>" [--k N]         # passthrough to memory /recall
ops-memory backups [--json]                 # list 12TB ArangoDB backups + retention
ops-memory backup [--now]                   # create a dump on the 12TB drive (ops-arango)
ops-memory fix [--apply]                    # plan/trigger memory-repo migration
ops-memory config doctor [--json]           # non-interactive readiness
```

## The metrics matrix (why this skill exists)

`metrics` joins per-collection facts from `ops-arango coverage` (counts, index
inventory, **ArangoSearch view membership**, named-graph membership,
LIMIT-bounded Qdrant-pointer sampling, index-backed latest timestamp) with
`ops-qdrant` health, and derives one row per collection. Each row reports its
`recall_lanes` — any of **bm25** (an ArangoSearch view links it), **dense** (it
has Qdrant vectors), **graph** (edge / named-graph member reachable by multi-hop
traversal) — plus a `recall_connected` boolean and these flags:

| Flag | Meaning |
|---|---|
| `not_recall_connected` | **no bm25, dense, or graph lane — invisible to `/memory recall`** |
| `no_arangosearch` | document collection linked in no ArangoSearch view — no BM25/text lane |
| `bm25_only` / `no_qdrant_embedding` | document collection with **0%** Qdrant pointers — no dense/semantic lane |
| `partial_sync` | some, not all, docs vector-synced (0% < frac < 90%) |
| `no_secondary_index` | only the primary/edge index — no query index |
| `slow_scan_risk` | ≥50k docs **and** no secondary index — query-performance risk |
| `embedding_array_violation` | Arango is holding embedding arrays (contract breach; see best-practices-arangodb rule 22) |
| `empty` | zero documents |
| `stale` | latest **indexed** timestamp older than `--stale-days` |

The report also carries a `recall_connectivity` summary (`connected`,
`not_connected`, `non_empty`). Staleness is asserted **only** where a timestamp
index makes it cheap to prove; otherwise the row reports
`latest_timestamp: unknown` (never fabricated). Edge collections are exempt from
`bm25_only`/`no_arangosearch` (they carry no embeddings and no text view) and are
counted recall-connected through the graph lane.

## Backups on the 12TB drive

`ops-arango dump` already writes to `/mnt/storage12tb/backups/arangodb` with
retention (keep last 7). ops-memory surfaces that as one call:

```
ops-memory backups          # what backups exist, sizes, newest first
ops-memory backup --now     # take a fresh dump on the 12TB drive now
```

## Progressive disclosure

- Layer 1: this frontmatter (routing).
- Layer 2: this SKILL.md (command map + boundary).
- Layer 3: `scripts/ops_memory.py` (typed seams, flag logic), plus
  `docs/PROJECT_KNOWLEDGE.md` (verified topology + known gaps).

## Readiness

Complex orchestrator. `sanity.sh` is the offline behavioral + safety gate
(topology/config-doctor contracts, no-direct-DB-access, no `shell=True`, and a
fail-closed negative control). `sanity-e2e.sh` is the opt-in **live** gate — it
calls the real ops-arango/ops-qdrant/phart entrypoints, asserts the merged
schemas and `seam_validation=PASS`, and fails closed on a missing downstream
receipt. Never mark a feature READY on exit-0 alone. See
`fixtures/agentic_eval.json` for the positive/negative/adversarial cases.
