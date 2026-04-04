---
name: memory
description: >
  MEMORY FIRST - Query memory BEFORE scanning any codebase. Use when encountering
  ANY problem, error, or task. Call "recall" FIRST, then scan codebase only if
  nothing found. Triggers: "check memory", "recall", "have we seen", "remember how".
allowed-tools: Bash, Read
triggers:
  - check memory
  - recall
  - clarify
  - have we seen this
  - remember how we solved
  - what did we learn
  - recall previous
  - save this lesson
  - learn from this
  - check memory for
  - have we seen this before
  - query memory first
  - ask clarifying questions
  - doesn't understand
metadata:
  short-description: MEMORY FIRST - Query before scanning codebase
provides:
  - memory-recall
  - memory-learn
  - edge-verification
composes:
  - extractor
  - edge-verifier
  - taxonomy
  - embedding
  - task-monitor

taxonomy:
  - knowledge
  - persistence
  - resilience
  - precision
docs:
  arangodb: /best-practices-arangodb
---

> **STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.**
> Do not skim. Do not skip to the code examples. This document contains
> unique constraints, deterministic `_key` rules, secondary unique indexes,
> embedding dimension requirements (384), and schema ownership rules that
> WILL cause silent data corruption or 400/409 errors if you ignore them.
> Every section exists because an agent broke something by not reading it.

# Memory Skill - MEMORY FIRST Pattern

Pi is the only CLI agent that can reliably enforce Memory First (other CLIs treat pre-hooks as optional), so this skill is the **front-door contract** for Pi and humans alike.

**Non-negotiable rule**: Query memory BEFORE scanning any codebase.

## Commands Snapshot

| Command                                           | Use Case                                                               |
| ------------------------------------------------- | ---------------------------------------------------------------------- |
| `./run.sh recall --q "..."`                       | FIRST step for every task                                              |
| `./run.sh learn --problem "..." --solution "..."` | After solving something new                                            |
| `./run.sh clarify --q "..."`                      | Detect ambiguity + generate clarifying questions when recall is weak    |
| `./run.sh preset compile --ids '{"set":"..."}'`   | Compile deterministic technical specs from ArangoDB                    |
| `./run.sh preset sanity`                          | Audit preset library for broken links / cycles (Strict Mode)           |
| `./run.sh info`                                   | Print active configuration (embedder, episodic sources, edge verifier) |
| `./run.sh serve --host --port`                    | Keep the FastAPI server warm for low-latency recall                    |
| `./run.sh status`                                 | Quick health check / Arango connectivity                               |

## Daemon HTTP Endpoints

Memory service runs as a Docker container on `http://127.0.0.1:8601`.

### POST /recall — Semantic Search (BM25 + cosine + graph traversal)

The primary search endpoint. Searches across lessons and SPARTA collections using
BM25 lexical matching, cosine similarity (via embedding service), and multi-hop
graph traversal (via `sparta_relationships` edges). Returns ranked results with
per-item scores and a combined `confidence` value.

```python
import httpx

transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
client = httpx.Client(transport=transport, base_url="http://localhost")

# Search all collections (lessons + SPARTA supplemental)
r = client.post("/recall", json={"q": "jamming satellite Telestar", "k": 5})
data = r.json()
# data = {
#   "found": True,
#   "should_scan": False,
#   "confidence": 27.988,         ← combined BM25+cosine+graph score
#   "items": [                    ← NOT "results" — the key is "items"
#     {
#       "_key": "...",
#       "scores": {               ← per-item breakdown
#         "bm25": 1.0,            ← BM25 reciprocal rank (0-1)
#         "graph": 0.5,           ← graph traversal score (0-1)
#         "dense": 0.39,          ← cosine similarity (0-1, requires vector-store)
#         "freshness": 0.87       ← time decay (0-1)
#       },
#       ...
#     }
#   ],
#   "meta": {"took_ms": 42, "supplemental_count": 10}
# }

# Search specific SPARTA collection for citation grounding
r = client.post("/recall", json={
    "q": "Cuban operators at the Bejucal electronic-warfare site",
    "k": 3,
    "collections": ["sparta_url_knowledge"],  # target specific corpus
})
```

**Parameters:**
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | str | required | Search query text |
| `k` | int | 5 | Max results to return |
| `scope` | str | `""` | Project scope filter |
| `threshold` | float | 0.3 | Minimum confidence to consider "found" |
| `collections` | list | null | Target specific collections (null=all) |
| `tags` | list | null | Filter by tags |

**Response:** `{found, should_scan, confidence, items, meta, errors}`.
- `items` (NOT `results`) — ranked list of matching documents
- `confidence` — combined score from top items (BM25 × 0.6 + graph × 0.4 for lessons, BM25 only for SPARTA)
- Each item has `scores: {bm25, graph, dense, freshness}` breakdown
- When `collections` targets SPARTA collections, results come from supplemental sources via ArangoSearch View
- `dense=0.0` means vector-store is down — check `docker ps | grep vector-store`

**CRITICAL:** The daemon proxy runs `MemoryClient.recall()` locally (not just HTTP forwarding). Code changes to `api.py` require `uv pip install -e . && systemctl --user restart embry-memory`. The Docker container at 8601 has its own code copy — it does NOT auto-reload from host source files.

#### CORRECT usage — via Unix socket, read `items` and `confidence`:
```python
import httpx

transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
client = httpx.Client(transport=transport, base_url="http://localhost")
resp = client.post("/recall", json={"q": "jamming satellite", "k": 5})
data = resp.json()

if data["found"]:
    for item in data["items"]:       # ← "items" NOT "results"
        print(item["scores"])         # ← {bm25, graph, dense, freshness}
    print(data["confidence"])         # ← combined grounding signal
```

## Common Mistakes

Agents make these mistakes **every session**. Read before using.

```python
# WRONG: "results" does not exist — the key is "items"
data.get("results", [])              # ← returns [] always
# RIGHT:
data["items"]                        # ← correct key

# WRONG: curl to localhost:8601 (TCP)
curl http://localhost:8601/recall
# RIGHT: use httpx with Unix socket
transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
client = httpx.Client(transport=transport, base_url="http://localhost")
resp = client.post("/recall", json={"q": query, "k": 5})

# WRONG: subprocess.run(["memory/run.sh", "recall", ...]) in a loop
# → 2s overhead per call, fork-bomb risk (learn-datalake incident: 79 processes, 141GB RAM)
# RIGHT: httpx client reuses connection pool
for item in batch:
    resp = client.post("/recall", json={"q": item, "k": 3})

# WRONG: from graph_memory.api import MemoryClient
# → bypasses daemon, no BM25/graph scoring, no embedding integration
# RIGHT: always use HTTP client to daemon (above)

# WRONG: import requests; requests.post("http://127.0.0.1:8601/recall", ...)
# → 120s default timeout, no Unix socket support
# RIGHT: import httpx with explicit timeout
resp = client.post("/recall", json={...}, timeout=httpx.Timeout(10.0, connect=2.0))

# WRONG: building manual corpus with rapidfuzz instead of reading confidence
for doc in manually_fetched_docs:     # ← STOP. Just read data["confidence"].
    fuzz.partial_ratio(...)           #    The daemon already did BM25+cosine+graph.

# WRONG: reimplementing /recall with per-collection /list calls
for coll in ["sparta_controls", "sparta_url_knowledge"]:
    resp = client.post("/list", ...)  # ← STOP. /recall already searches all
    corpus += resp["documents"]       #    collections via the unified View.
# RIGHT: single /recall call with collections param
resp = client.post("/recall", json={"q": query, "k": 10,
    "collections": ["sparta_controls", "sparta_url_knowledge"]})

# WRONG: writing raw AQL outside the memory project
db.aql.execute("FOR doc IN lessons FILTER ...")
# → ALL AQL must reside ONLY in ~/workspace/experiments/memory/
# RIGHT: use /recall, /list, /analytics/run endpoints

# WRONG: /memory learn without taxonomy tags
./run.sh learn --problem "X" --solution "Y"
# RIGHT: include bridge tags so /recall can find it later
./run.sh learn --problem "X" --solution "Y" --tag "Fragility" --tag "extraction"

# WRONG: ignoring should_scan in recall response
if data["found"]: return data["items"]
# RIGHT: check should_scan for hybrid recall+codebase search
if data["found"] and data["confidence"] > 0.5: return data["items"]
elif data.get("should_scan"): return merge(data["items"], scan_codebase(query))
```


See [TOM.md](references/TOM.md) for Theory of Mind (ToM) persona agent commands, context/commiseration, deep analysis, and graph traversal.

See [ARCHITECTURE.md](references/ARCHITECTURE.md) for the control extraction pipeline, edge collections, and 3-tier extraction architecture.

See [API.md](references/API.md) for /list, /upsert, /recall/by-keys endpoints, schema management, embedding reference, layout controls, common memory client, Python API, and configuration.
