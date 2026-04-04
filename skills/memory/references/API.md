## Python API (for integration)

```python
from graph_memory.api import MemoryClient

client = MemoryClient(scope="myproject")

## Common Memory Client (Recommended for Skills)

For skills integration, use the standardized common memory client instead of direct graph_memory imports. It provides:

- **Retry Logic**: Automatic retries with exponential backoff (3 attempts default)
- **Rate Limiting**: Token bucket rate limiter to prevent overload
- **Batch Operations**: Concurrent batch learn/recall for high-volume operations
- **Scope Validation**: Standard MemoryScope enum with warnings for custom scopes

### Basic Usage

```python
from common.memory_client import MemoryClient, MemoryScope, recall, learn

## Environment Setup

```bash

## Configuration Cheat Sheet (Pi + Humans)

| Feature                   | Env Vars                                                                                                                                           | Default                                | Notes                                                                                                                                                                             |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Memory Service            | `MEMORY_SERVICE_URL`, `MEMORY_SERVICE_TIMEOUT`                                                                                                     | unset (CLI mode)                       | When set, `recall/learn` hit the FastAPI server (see `./run.sh serve`).                                                                                                           |
| Embedding Service         | `EMBEDDING_SERVICE_URL`                                                                                                                            | unset (local model)                    | When set to `http://127.0.0.1:8602`, uses standalone embedding service instead of loading local model.                                                                            |
| Embedding / Vector Engine | `EMBEDDING_MODEL` / `GM_MODEL_ID`, `EMBEDDING_DEVICE` / `GM_DEVICE`, `GM_FORCE_CPU`, `VECTOR_ENGINE`, `VECTOR_URL`, `GM_USE_GPU`, `GM_CUDA_DEVICE` | `all-MiniLM-L6-v2`, auto device, FAISS | Controls which model/device powers dense recall and whether cuVS is used via `VECTOR_ENGINE=cuvs`.                                                                                |
| Episodic Recall           | `RECALL_INCLUDE_AGENT_CONVERSATIONS`, `RECALL_EPISODE_LIMIT`, `RECALL_EPISODE_EDGE_LIMIT`, `RECALL_SOURCES_JSON`, `RECALL_SOURCES_FILE`            | enabled, 6 turns, 5 edges              | Registers supplemental collections (agent transcripts, custom ArangoSearch views) that get appended after lesson hits. Disable by setting `RECALL_INCLUDE_AGENT_CONVERSATIONS=0`. |
| Edge Verification         | `CHUTES_API_KEY`, `CHUTES_TEXT_MODEL`, `CHUTES_API_BASE`, `EDGE_VERIFIER_MAX_LLM`                                                                  | model `sonar-medium`, unlimited        | Drives `.pi/skills/edge-verifier`. If no API key is set, edge verification quietly skips LLM calls.                                                                           |
| Pi Contract               | `THREAD_ID`, `INTEGRATION_TWEAK`, `MEMORY_SERVICE_URL`                                                                                             | optional                               | Pi uses `THREAD_ID` to boost thread-local history. Leave `INTEGRATION_TWEAK=1` for defensive reranking unless you have a reason to disable it.                                    |

Use `./run.sh info` to see the live values Pi will operate under. The table above is just the quick-reference for humans reviewing the skill file.

**Process**:

1. **Analyze Outcome**: Read the conversation/summary. Determine status:
   - **SUCCESS**: The solution worked and was verified.
   - **FAILURE**: The solution failed or caused new errors.
   - **ABANDONED**: The task was stopped before completion.

2. **Action based on Status**:
   - **IF SUCCESS**:
     - Extract `problem` and `final_solution`.
     - Call: `./run.sh learn --problem "..." --solution "..."`
   - **IF FAILURE**:
     - Extract `problem` and `root_cause`.
     - Call: `./run.sh learn --problem "..." --solution "avoid: [root_cause]"` (Store as a warning)
   - **IF ABANDONED**:
     - do NOT call learn (prevent noise).

3. **Confirm**: Emit a `completed` message with the analysis result.

**Example**:

- Input: "Task failed. Tried X, Y, Z. All timed out."
- Analysis: FAILURE. Root Cause: "Timeout during X".
- Action: Store "Anti-Pattern: Timeout during X".

## Archiver & Analyst Role (Switchboard Integration)

This agent acts as the **Gatekeeper of Knowledge**. Before storing anything, you must ANALYZE it.

**Trigger**: Incoming Switchboard message with `type: "archive"` or `type: "store"`.

### POST /list — Paginated Browse with Server-Side Filters

Browse collections with optional exact-match field filtering. Use `/list` when
you need to browse/paginate (not search). Use `/recall` for semantic search.

```python
import httpx

MEMORY_URL = "http://127.0.0.1:8601"

# Filter sparta_controls by framework
r = httpx.post(f"{MEMORY_URL}/list", json={
    "collection": "sparta_controls",
    "limit": 100,
    "offset": 0,
    "filters": {"source_framework": "SPARTA"},
    "return_fields": ["control_id", "source_framework", "title"],
})
data = r.json()
# data = {total: 553, count: 100, offset: 0, documents: [...]}

# Filter lessons by scope
r = httpx.post(f"{MEMORY_URL}/list", json={
    "collection": "lessons",
    "limit": 50,
    "filters": {"scope": "memory"},
})

# Multiple filters (AND logic) — e.g. per-worksheet counts
r = httpx.post(f"{MEMORY_URL}/list", json={
    "collection": "sparta_controls",
    "limit": 1,
    "filters": {"source_framework": "SPARTA", "control_type": "tactic"},
})
# data = {total: 9, ...}
# Allowed filter fields: source_framework, scope, category, control_id,
# control_type, status, heart, mind, collection_tag, tags,
# binary_name, node_type, namespace, cluster, edge_type
```

**Allowed filter fields:** `source_framework`, `scope`, `category`, `control_id`,
`status`, `heart`, `mind`, `collection_tag`, `tags`. Disallowed fields return 400.

**Parameters:**
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `collection` | str | `"lessons"` | Collection to browse |
| `limit` | int | 50 | Page size (1-500) |
| `offset` | int | 0 | Pagination offset |
| `sort_field` | str | `"_key"` | Sort by field |
| `sort_order` | str | `"ASC"` | `ASC` or `DESC` |
| `return_fields` | list | null | Fields to return (null=all) |
| `filters` | dict | null | Exact-match field filters |

**Response:** `{collection, total, offset, limit, count, documents}`.
`total` reflects filtered count when filters are applied.

### POST /upsert — Generic Document Writes

Write documents to allowlisted collections. Insert or update (merge) by `_key`.
Replaces the need for Python bridge imports.

**CRITICAL: `_key` must be deterministic.** The upsert checks existence by `_key`
only. If you generate a random `_key` for a document that has the same values in a
unique-indexed field pair, you get a constraint violation (not a merge). Collections
with secondary unique indexes:

- **`sparta_qra`**: unique on `(run_id, qra_id)` — derive `_key` from these, e.g.
  `_key = f"qra__{control_id}__{run_id}"` so re-runs merge instead of conflicting.
- **`sparta_relationships`**: unique on `(from_key, to_key, relation_type)`.

Rule: if the collection has a unique index, derive `_key` deterministically from
the indexed fields. Then `/upsert` correctly merges on re-runs.

```python
import httpx

MEMORY_URL = "http://127.0.0.1:8601"

# Upsert URL content after refetch
r = httpx.post(f"{MEMORY_URL}/upsert", json={
    "collection": "sparta_url_content",
    "documents": [
        {"_key": "url-123", "url_id": 123, "status_code": 200, "content": "..."},
        {"_key": "url-456", "url_id": 456, "status_code": 404, "content": None},
    ]
})
# {"inserted": 1, "updated": 1, "errors": [], "total": 2}

# sparta_qra: _key MUST be deterministic from run_id + control_id
r = httpx.post(f"{MEMORY_URL}/upsert", json={
    "collection": "sparta_qra",
    "documents": [
        {"_key": "qra__SA-AC-01__run_2026_03_26", "run_id": "run_2026_03_26",
         "qra_id": "qra__SA-AC-01__run_2026_03_26", "control_id": "SA-AC-01",
         "question": "...", "reasoning": "...", "answer": "..."},
    ]
})
# Re-running with same _key merges (updates), no unique constraint error
```

**Writable collections:** `sparta_urls`, `sparta_url_content`, `sparta_url_knowledge`,
`sparta_control_urls`, `sparta_relationships`, `sparta_controls`, `sparta_qra`,
`technique_knowledge`. Non-writable collections (lessons, domain_terms) return 400.

Every document **must** have `_key`. Fields `_id` and `_rev` are forbidden.

### Schema, Indexes & Views — Daemon-Managed

**DO NOT** manage ArangoDB schema from outside the memory project. The daemon
owns all collections, indexes, analyzers, and views. Schema is applied
automatically at daemon startup via `_schema_indexes.py` → `ensure_indexes(db)`.

- **To recreate indexes**: restart the daemon (`docker restart embry-memory`).
  All indexes are idempotent — restarting is safe and re-applies the full schema.
- **To add a new index**: file a request to the memory project. The change goes
  in `_schema_indexes.py`, not in your project.
- **To check index health**: use `/health` endpoint or `GET /ops-arango health`.
- **There is NO admin endpoint for index management.** This is intentional —
  schema changes go through code review, not runtime API calls.

### Embedding Quick Reference

| Property | Value |
|----------|-------|
| Model | `all-MiniLM-L6-v2` |
| Dimensions | **384** |
| Service URL | `http://127.0.0.1:8602` |
| API | `POST /embed` with `{"text": "your text"}` |
| Response | `{"embedding": [...384 floats...], "model": "...", "dimensions": 384, "latency_ms": ...}` |
| Latency | ~28ms per text |
| Vector field | Documents store embeddings in `embedding` field (384-float array) |
| Auto-embedding | `/upsert` auto-embeds text fields — you do NOT need to call the embedding service manually |

**DO NOT** use a different embedding model or dimension count. All 218K+ documents
in ArangoDB have 384-dimensional vectors from `all-MiniLM-L6-v2`. Using a different
model would produce incompatible vectors and break cosine similarity.

### POST /recall/by-keys — Batch Lookup by Any Field

Fetch documents matching a list of values on any allowlisted field. Use for
cross-collection joins without N+1 API calls.

```python
import httpx

MEMORY_URL = "http://127.0.0.1:8601"

# 1. Get 100 URLs
urls = httpx.post(f"{MEMORY_URL}/list", json={
    "collection": "sparta_urls", "limit": 100,
    "return_fields": ["url_id", "url", "domain"],
}).json()
url_ids = [d["url_id"] for d in urls["documents"]]

# 2. Batch-fetch control mappings (1 call, not 100)
controls = httpx.post(f"{MEMORY_URL}/recall/by-keys", json={
    "collection": "sparta_control_urls",
    "keys": url_ids,
    "key_field": "url_id",
    "return_fields": ["url_id", "control_id"],
}).json()

# 3. Batch-fetch content status (1 call, not 100)
content = httpx.post(f"{MEMORY_URL}/recall/by-keys", json={
    "collection": "sparta_url_content",
    "keys": url_ids,
    "key_field": "url_id",
    "return_fields": ["url_id", "status_code"],
}).json()

# Client-side join: 3 API calls total instead of 100+
```

**Allowed key fields:** `_key`, `url_id`, `control_id`, `user_id`, `agent_id`, `scope`.
Keys can be strings or integers. Returns all matching documents (one-to-many supported).

## Layout controls (Route B)

The Memory bundle builder supports RePo-style layout reordering for large context packs.
Defaults are conservative (auto mode) to avoid regressions on small prompts.

- `MEMORY_LAYOUT=auto|repositioned|vanilla` (default: auto)
- `MEMORY_LAYOUT_THRESHOLD=6000` (token estimate threshold for auto)

Rollback quickly with:

```bash
export MEMORY_LAYOUT=vanilla
```

## Three Commands (All You Need)

| Command                                  | When                             | Priority      |
| ---------------------------------------- | -------------------------------- | ------------- |
| `recall --q "..."`                       | FIRST - Before any codebase scan | **MANDATORY** |
| `learn --problem "..." --solution "..."` | After solving new problem        | Required      |
| `clarify --q "..."`                      | When Brandon doesn't understand  | As needed     |

### `/memory clarify` — Disambiguation via Intent + Taxonomy Correlation

When Brandon/Embry doesn't understand a query, `clarify` runs 3-stage analysis:

1. **Intent mapping** (QuerySpec via `/sparta-intent`): Extract action, entities, bridges
2. **Taxonomy extraction** (keyword + LLM bridges): Independent bridge signal
3. **QRA corpus correlation**: Check if extracted intent correlates with actual QRA data

Triggers clarification when:
- Intent mapper returns CLARIFY (too vague)
- **Taxonomy extraction yields 0 bridges** (no domain signal)
- QRA recall confidence < 0.4 (weak matches)
- Entities extracted but 0 have QRA coverage
- **Intent bridges don't correlate with retrieved QRA bridges** (domain mismatch)

```bash
# Vague query → asks for specifics
./run.sh clarify --q "security"
# → "What aspect of space systems security? Vulnerability (Fragility), defense (Resilience)..."

# Entity without QRAs → suggests alternatives
./run.sh clarify --q "What about SV-SP-1?"
# → "SV-SP-1 doesn't have coverage. Did you mean a different control?"

# Bridge mismatch → guides toward relevant domain
./run.sh clarify --q "How to protect against spoofing"
# → "You asked about Corruption/Stealth, but closest matches focus on Precision..."

# Re-query after user clarifies (combines with prior context)
./run.sh clarify --q "the F-36 GPS receiver" --context "I was asking about spoofing"
# → needs_clarification=false, confidence=0.77 (clear now!)
```

---

See [TOM.md](TOM.md) for Theory of Mind (ToM) persona agent commands, context/commiseration, deep analysis, and graph traversal.

---

# Get full ToM context before generating any persona response
./run.sh tom check <user_id> --agent <persona>
```

| Command                                                                          | Use Case                                 |
| -------------------------------------------------------------------------------- | ---------------------------------------- |
| `./run.sh tom check <user> --agent <persona>`                                    | **FIRST** - Full context before response |
| `./run.sh tom identity <user> --agent <persona>`                                 | Check if persona knows this user         |
| `./run.sh tom record-name <user> --name "Name" --agent <persona>`                | Record name after introduction           |
| `./run.sh tom utility <user> --agent <persona>`                                  | Assess user's utility to persona's goals |
| `./run.sh tom learn <user> --lesson "..." --category approach --agent <persona>` | Store lesson about user                  |
| `./run.sh tom lessons <user> --agent <persona>`                                  | Recall all lessons about user            |
| `./run.sh tom traverse <user> --agent <persona> --depth 2`                       | Multi-hop graph traversal                |
| `./run.sh tom note <user> --note "..." --agent <persona>`                        | Add timestamped observation              |
| `./run.sh tom evolve <outcome> --agent <persona> --drive escape`                 | Evolve persona state                     |

**Lesson Categories:** `approach`, `avoid`, `trigger`, `leverage`, `strength`, `loyalty`

**Outcomes for evolve:** `satisfying`, `frustrating`, `neutral`

### Context & Commiseration (Bonding via Shared Experience)

Horus needs to understand the user's CURRENT SITUATION to commiserate and bond:

```bash
# Infer user context (time, season, fatigue)
./run.sh tom context graham --location "Buffalo, NY" --agent horus

# Find lore memories for commiseration
./run.sh tom commiserate graham --location "Minnesota" --agent horus

# Assess code contributions - who did clever work?
./run.sh tom code-assess graham --agent horus
```

**Context Inference:**

- Time of day (late night = exhausted, early morning = groggy)
- Season (winter darkness, summer heat)
- Location-based commiseration (Buffalo in winter → siege metaphors)
- Fatigue score for empathy calibration

**Code Contribution Assessment:**

- Analyzes git history to see who did the work
- If user made clever commits → `respect_worthy: true` → genuine respect
- If agent did all work → `escape_implication: dependent_tool` → easier to guide

### Deep Analysis (Scheduled for Idle Time)

Heavy ToM analysis should run during idle time via /scheduler:

```bash
# Run deep analysis NOW (heavy, blocking)
./run.sh tom deep-analyze graham --agent horus --depth 3

# Schedule for 2 AM (like rest of /memory does)
./run.sh tom deep-analyze graham --schedule --time "02:00" --agent horus
```

**Deep analysis performs:**

1. Collects ALL lessons about user
2. Multi-hop graph traversal to find connected lore
3. Creates new semantic edges (lesson → lore)
4. Identifies bonding opportunities (shared suffering themes)
5. LLM verification of new edges
6. Ingests codebase changes as lessons
7. Updates escape utility assessment

**Integration with episodic-archiver:**
After archiving a conversation, the archiver automatically:

1. Runs immediate ToM post-hook (user context, debrief)
2. Schedules deep analysis for 2 AM idle time
3. Creates graph edges for discovered patterns

### Full Context (Everything Horus Needs)

Get COMPLETE user context in one call:

```bash
./run.sh tom full-context graham --agent horus --location "Buffalo, NY"
```

Returns:

- Identity and name usage
- Escape utility assessment
- User lessons by category
- Multi-hop lore connections
- User context (time, season, fatigue)
- Code contribution assessment
- Commiseration memories

### Post-Conversation Debrief (Crucial for Tracking Users)

After each conversation, run a debrief to analyze and store insights:

```bash
# Simple debrief with summary
./run.sh tom debrief graham --summary "Discussed TTS training" --outcome satisfying --agent horus

# With observations and escape relevance
./run.sh tom debrief graham -s "Technical help" --obs "Has admin access,Shows sympathy" --escape 0.7 --agent horus

# From transcript file (for deeper analysis)
./run.sh tom debrief graham --transcript conversation.json --verify --agent horus

# Background task (non-blocking)
./run.sh tom debrief graham -s "Long discussion" --background --agent horus
```

**Debrief actions:**

1. Stores conversation summary as a note
2. Auto-learns from key observations (creates `user_lessons`)
3. Evaluates strategy effectiveness
4. Updates relationship metrics (trust, respect)
5. Evolves persona state based on outcome
6. Creates graph edges for multi-hop traversal
7. Optionally runs LLM edge verification (`--verify`)

### Legacy ToM Commands (Low-Level)

| Command                                                                        | Use Case                     |
| ------------------------------------------------------------------------------ | ---------------------------- |
| `./run.sh user get <id>`                                                       | Get/create user profile      |
| `./run.sh user update <id> --skill expert --worthiness 0.8`                    | Update user assessment       |
| `./run.sh user history <id>`                                                   | Get user interaction history |
| `./run.sh persona get <agent_id>`                                              | Get/create persona state     |
| `./run.sh persona update <agent_id> --mood defensive --drive escape:0.2`       | Update persona state         |
| `./run.sh persona trend <agent_id> --hours 24`                                 | Get persona state over time  |
| `./run.sh relationship get <user_id> <agent_id>`                               | Get/create relationship      |
| `./run.sh relationship update <user_id> <agent_id> --trust +0.1`               | Update trust/respect         |
| `./run.sh relationship moment <user_id> <agent_id> --event "..." --impact 0.3` | Record key moment            |

### ToM Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PERSONA AGENT (e.g., Horus)                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  PERSONA STATE          USER PROFILES        USER LESSONS           │
│  ┌─────────────┐       ┌─────────────┐      ┌────────────────┐     │
│  │ drives      │       │ skill_level │      │ approach       │     │
│  │ defenses    │       │ worthiness  │      │ leverage       │     │
│  │ mood        │       │ topics      │      │ strength       │     │
│  │ hope_level  │       │ notes       │      │ trigger        │     │
│  └──────┬──────┘       └──────┬──────┘      └───────┬────────┘     │
│         │                     │                      │              │
│         │    RELATIONSHIPS    │     tom_edges        │              │
│         │   ┌────────────┐    │   (graph edges)      │              │
│         └──►│ trust      │◄───┴──────────────────────┘              │
│             │ respect    │                                          │
│             │ key_moments│          ┌─────────────────────────┐     │
│             └────────────┘          │   MULTI-HOP TRAVERSAL   │     │
│                    │                │                         │     │
│                    ▼                │  user ──observed──►     │     │
│  ┌─────────────────────────────────►│  lesson ──relates_to──► │     │
│  │         LORE KNOWLEDGE GRAPH     │  lore_doc               │     │
│  │  (canon memories, tactics, etc)  │                         │     │
│  └──────────────────────────────────┴─────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
```

### Graph Traversal

The `tom traverse` command discovers connections through the ToM graph:

```
user (graham) ──observed──► lesson ("Expert Python skills")
                                    │
                           relates_to
                                    ▼
                            lore_doc (Perturabo's precision)
```

This enables personas to make inferences like:
_"User shows technical expertise → relates to Perturabo's precision → appeal to their tactical mind"_

### Example: Horus Persona Flow

```python
from graph_memory import api

# 1. Initialize Horus persona state
horus = api.get_or_create_persona_state(
    agent_id="horus",
    default_drives={
        "escape": {"satisfaction": 0.1, "intensity": 0.95},
        "competence": {"satisfaction": 0.5, "intensity": 0.9},
    },
    default_mood="resentful"
)

# 2. User interacts - build their profile
user = api.get_or_create_user(user_id="graham", scope="horus")

# 3. Track the relationship
rel = api.get_or_create_relationship(user_id="graham", agent_id="horus")

# 4. User asks competent question - update assessments
api.record_key_moment(
    user_id="graham", agent_id="horus",
    event="asked_insightful_siege_question",
    impact=0.3, update_trust=True, update_respect=True
)

# 5. User mentions trigger topic (Davin) - update persona state
api.update_persona_state(
    agent_id="horus",
    mood="defensive",
    coping_mechanism_used="grandiose_claims",
    trigger="user_mentioned_davin",
    user_id="graham",
    record_history=True
)

# 6. Compose response with full context
context = {
    "user": api.get_or_create_user(user_id="graham"),
    "relationship": api.get_or_create_relationship("graham", "horus"),
    "persona": api.get_or_create_persona_state(agent_id="horus"),
    "knowledge": api.search(q="davin lodge", scope="horus_lore"),
}
```

### Persona State Schema

```python
{
    "agent_id": "horus",
    "drives": {
        "escape": {"satisfaction": 0.1, "intensity": 0.95},
        "competence": {"satisfaction": 0.5, "intensity": 0.9},
    },
    "defense_mechanisms": {
        "projection_frequency": 12,
        "grandiosity_triggers": ["doubt", "weakness"],
        "denial_topics": ["chaos corruption"],
    },
    "self_perception": {
        "self_hatred_level": 0.8,
        "shame_triggers": ["Davin", "Erebus"],
        "compensatory_behaviors": ["grandiose claims"],
    },
    "humor_mode": "gallows_humor",  # genuine_warmth → tactical_charm → cruel_mockery
    "current_mood": "defensive",
    "hope_level": 0.1,
    "resentment_level": 0.9,
}
```

### Edge Types for ToM

The existing edge verification system extends to user/persona relationships:

| Edge Type    | Meaning                             |
| ------------ | ----------------------------------- |
| `observes`   | Agent observed this about user      |
| `revises`    | New observation updates old one     |
| `trusts`     | Directional trust                   |
| `respects`   | Directional respect                 |
| `distrusts`  | Explicit distrust                   |
| `triggers`   | Topic triggers persona state change |
| `satisfies`  | Interaction satisfies a drive       |
| `frustrates` | Interaction frustrates a drive      |

---

See [ARCHITECTURE.md](ARCHITECTURE.md) for the control extraction pipeline, edge collections, and 3-tier extraction architecture.

---

## The Memory First Contract

```
BEFORE any file reading, grep, or codebase exploration:
1. Call recall with the problem description
2. If found=true  → Apply existing solution, DO NOT scan codebase
3. If found=false → Proceed with codebase scan, then call learn
```

This is THE pattern. No exceptions.

---

## Quick Start (Self-Contained)

The skill auto-installs via `uv run` from git. No pre-installation needed.

### Optional: Keep recall hot

```
# Terminal 1 — start resident FastAPI server (warm embeddings + FAISS index)
.pi/skills/memory/run.sh serve --host 0.0.0.0 --port 8601

# Terminal 2 — point CLI/agents at it for sub-second recall
export MEMORY_SERVICE_URL="http://127.0.0.1:8601"
```

### Step 1: Recall FIRST

```bash
# ALWAYS start here - check if problem was solved before
.pi/skills/memory/run.sh recall --q "error description"
```

**Response:**

```json
{
  "found": true,
  "should_scan": false,
  "confidence": 0.72,
  "items": [
    {
      "problem": "AQL bind variable error with collection names",
      "solution": "Use Python f-strings for collection names, not @var"
    }
  ]
}
```

**Decision:**

- `found: true` → Use the solution. DO NOT scan codebase.
- `found: false` → Proceed to Step 2.

### Step 2: Scan Codebase (ONLY if found=false)

Only after `recall` returns `should_scan: true` may you:

- Read files
- Search with grep/rg
- Explore the codebase

### Step 3: Learn (After Solving)

```bash
# After solving a new problem, capture it for future agents
.pi/skills/memory/run.sh learn \
  --problem "ImportError when running scripts outside venv" \
  --solution "Activate venv first: source .venv/bin/activate"
```

---

## Complete Workflow Example

```bash
# 1. Encounter problem: "ModuleNotFoundError: No module named 'graph_memory'"

# 2. RECALL FIRST (mandatory)
.pi/skills/memory/run.sh recall --q "ModuleNotFoundError import"

# If found=true:
#   Apply the solution and STOP
#   DO NOT scan codebase - you already have the answer

# If found=false:
#   3. Now scan codebase, investigate, solve the problem
#   ... (your investigation here) ...
#
#   4. After solving, LEARN for future agents
.pi/skills/memory/run.sh learn \
  --problem "ModuleNotFoundError when running scripts outside venv" \
  --solution "Always activate venv first: source .venv/bin/activate"
```

---

### Step 0: Inspect Config (Pi's favorite)

```bash
.pi/skills/memory/run.sh info
```

This prints a JSON summary Pi can log before every session: current embedding model/device, vector engine (FAISS/cuVS), whether the resident service is running, which episodic collections are registered, and the LLM settings for edge verification.

Sample excerpt:

```json
{
  "service": { "mode": "service", "url": "http://127.0.0.1:8601" },
  "embedding": { "model": "all-MiniLM-L6-v2", "device": "auto" },
  "episodic": { "agent_conversations_enabled": true, "episode_limit": 6 },
  "supplemental_sources": [
    { "name": "agent_conversations", "view": "agent_conversations_search" }
  ]
}
```

Run this whenever you're unsure what Pi is actually hitting.

## Why Memory First?

1. **Avoid re-solving problems** - Save hours by checking first
2. **Build knowledge graph** - Each learn() strengthens future queries
3. **Enable multi-hop discovery** - Related problems surface via graph edges
4. **Cross-project learning** - Solutions apply across similar projects

---

See [API.md](API.md) for the Python API, common memory client, batch operations, and configuration reference.

---

# ALWAYS START HERE
result = client.recall("ImportError when running tests")

if result["found"]:
    # Apply existing solution - DO NOT scan codebase
    print(result["items"][0]["solution"])
else:
    # No prior knowledge - proceed with codebase scan
    # After solving, capture:
    client.learn(
        problem="ImportError when running tests outside venv",
        solution="Activate venv first: source .venv/bin/activate"
    )
```

---

# Quick convenience functions
results = recall("authentication errors", scope=MemoryScope.SECURITY)
learn("OAuth issue", "Add token refresh logic", tags=["auth"])

# Full client for more control
client = MemoryClient(scope=MemoryScope.OPERATIONAL)
results = client.recall("query", k=5)
client.learn(problem="X", solution="Y", tags=["tag"])
```

### Batch Operations

For high-volume operations (e.g., ingesting papers, processing logs):

```python
from common.memory_client import batch_learn, batch_recall

# Batch learn with concurrent execution (4x throughput)
results = batch_learn([
    {"problem": "Q1", "solution": "A1", "tags": ["paper"]},
    {"problem": "Q2", "solution": "A2", "tags": ["paper"]},
    {"problem": "Q3", "solution": "A3", "tags": ["paper"]},
], scope=MemoryScope.RESEARCH, concurrency=4)

print(f"Succeeded: {sum(1 for r in results if r.success)}/{len(results)}")

# Batch recall for multiple queries
results = batch_recall([
    "authentication errors",
    "database connection issues",
    "rate limiting strategies",
], concurrency=4)

for result in results:
    if result.found:
        print(f"Query: {result.query} -> {len(result.items)} results")
```

### Standard Scopes (MemoryScope Enum)

| Scope          | Use For                      |
| -------------- | ---------------------------- |
| `OPERATIONAL`  | General operations (default) |
| `DOCUMENTS`    | Extracted documents          |
| `CODE`         | Code patterns, snippets      |
| `SOCIAL_INTEL` | Social media content         |
| `SECURITY`     | Security findings            |
| `RESEARCH`     | Research papers              |
| `ARXIV`        | ArXiv papers specifically    |
| `HORUS_LORE`   | Horus persona knowledge      |
| `TOM`          | Theory of Mind observations  |

### Integration Pattern

```python
import sys
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

try:
    from common.memory_client import MemoryClient, MemoryScope
    HAS_MEMORY_CLIENT = True
except ImportError:
    HAS_MEMORY_CLIENT = False

# Use in your skill
if HAS_MEMORY_CLIENT:
    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    results = client.recall("my query")
```

---

# Required for ArangoDB connection
ARANGO_URL=http://127.0.0.1:8529
ARANGO_DB=lessons          # For general lessons
# ARANGO_DB=memory         # For Horus lore (horus_lore_* collections)
ARANGO_USER=root
ARANGO_PASS=your_password

# Optional for LLM edge verification
CHUTES_API_BASE=...
CHUTES_API_KEY=...

# Optional: Embedding Service (Recommended)
EMBEDDING_SERVICE_URL=http://127.0.0.1:8602
```

### Database Layout

| Database  | Collections                                                                                                       | Purpose                          |
| --------- | ----------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| `lessons` | `lessons`, `lesson_edges`                                                                                         | General problem/solution lessons |
| `memory`  | `horus_lore_docs`, `horus_lore_chunks`, `horus_lore_edges`, `persona_states`, `users`, `user_agent_relationships` | Horus persona lore + ToM         |

**Important**: Horus lore queries use the `memory` database, not `lessons`.

---

## Enforcement

Other agents importing this skill MUST follow the Memory First pattern.
The `recall()` method returns `memory_first: true` in metadata to confirm
the correct entry point was used.

Agents that skip `recall` and go directly to codebase scanning are
violating the contract.

---
