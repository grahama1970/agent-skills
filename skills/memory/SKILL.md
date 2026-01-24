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
  - have we seen this
  - remember how we solved
  - what did we learn
  - recall previous
  - save this lesson
  - learn from this
  - check memory for
  - have we seen this before
  - query memory first
metadata:
  short-description: MEMORY FIRST - Query before scanning codebase
---

# Memory Skill - MEMORY FIRST Pattern

Pi is the only CLI agent that can reliably enforce Memory First (other CLIs treat pre-hooks as optional), so this skill is the **front-door contract** for Pi and humans alike.

**Non-negotiable rule**: Query memory BEFORE scanning any codebase.

## Commands Snapshot

| Command                                           | Use Case                                                               |
| ------------------------------------------------- | ---------------------------------------------------------------------- |
| `./run.sh recall --q "..."`                       | FIRST step for every task                                              |
| `./run.sh learn --problem "..." --solution "..."` | After solving something new                                            |
| `./run.sh info`                                   | Print active configuration (embedder, episodic sources, edge verifier) |
| `./run.sh serve --host --port`                    | Keep the FastAPI server warm for low-latency recall                    |
| `./run.sh status`                                 | Quick health check / Arango connectivity                               |

## Two Commands (All You Need)

| Command                                  | When                             | Priority      |
| ---------------------------------------- | -------------------------------- | ------------- |
| `recall --q "..."`                       | FIRST - Before any codebase scan | **MANDATORY** |
| `learn --problem "..." --solution "..."` | After solving new problem        | Required      |

---

## Theory of Mind (ToM) for Persona Agents

The memory system extends beyond "lessons about problems" to "lessons about minds" - enabling AI personas like Horus to maintain psychological state, build user models, and track relationships.

### ToM Commands (Persona-Agnostic)

**Pre-Response Check (START HERE):**
```bash
# Get full ToM context before generating any persona response
./run.sh tom check <user_id> --agent <persona>
```

| Command | Use Case |
|---------|----------|
| `./run.sh tom check <user> --agent <persona>` | **FIRST** - Full context before response |
| `./run.sh tom identity <user> --agent <persona>` | Check if persona knows this user |
| `./run.sh tom record-name <user> --name "Name" --agent <persona>` | Record name after introduction |
| `./run.sh tom utility <user> --agent <persona>` | Assess user's utility to persona's goals |
| `./run.sh tom learn <user> --lesson "..." --category approach --agent <persona>` | Store lesson about user |
| `./run.sh tom lessons <user> --agent <persona>` | Recall all lessons about user |
| `./run.sh tom traverse <user> --agent <persona> --depth 2` | Multi-hop graph traversal |
| `./run.sh tom note <user> --note "..." --agent <persona>` | Add timestamped observation |
| `./run.sh tom evolve <outcome> --agent <persona> --drive escape` | Evolve persona state |

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

| Command | Use Case |
|---------|----------|
| `./run.sh user get <id>` | Get/create user profile |
| `./run.sh user update <id> --skill expert --worthiness 0.8` | Update user assessment |
| `./run.sh user history <id>` | Get user interaction history |
| `./run.sh persona get <agent_id>` | Get/create persona state |
| `./run.sh persona update <agent_id> --mood defensive --drive escape:0.2` | Update persona state |
| `./run.sh persona trend <agent_id> --hours 24` | Get persona state over time |
| `./run.sh relationship get <user_id> <agent_id>` | Get/create relationship |
| `./run.sh relationship update <user_id> <agent_id> --trust +0.1` | Update trust/respect |
| `./run.sh relationship moment <user_id> <agent_id> --event "..." --impact 0.3` | Record key moment |

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
*"User shows technical expertise → relates to Perturabo's precision → appeal to their tactical mind"*

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

| Edge Type | Meaning |
|-----------|---------|
| `observes` | Agent observed this about user |
| `revises` | New observation updates old one |
| `trusts` | Directional trust |
| `respects` | Directional respect |
| `distrusts` | Explicit distrust |
| `triggers` | Topic triggers persona state change |
| `satisfies` | Interaction satisfies a drive |
| `frustrates` | Interaction frustrates a drive |

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
.agents/skills/memory/run.sh serve --host 0.0.0.0 --port 8601

# Terminal 2 — point CLI/agents at it for sub-second recall
export MEMORY_SERVICE_URL="http://127.0.0.1:8601"
```

### Step 1: Recall FIRST

```bash
# ALWAYS start here - check if problem was solved before
.agents/skills/memory/run.sh recall --q "error description"
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
.agents/skills/memory/run.sh learn \
  --problem "ImportError when running scripts outside venv" \
  --solution "Activate venv first: source .venv/bin/activate"
```

---

## Complete Workflow Example

```bash
# 1. Encounter problem: "ModuleNotFoundError: No module named 'graph_memory'"

# 2. RECALL FIRST (mandatory)
.agents/skills/memory/run.sh recall --q "ModuleNotFoundError import"

# If found=true:
#   Apply the solution and STOP
#   DO NOT scan codebase - you already have the answer

# If found=false:
#   3. Now scan codebase, investigate, solve the problem
#   ... (your investigation here) ...
#
#   4. After solving, LEARN for future agents
.agents/skills/memory/run.sh learn \
  --problem "ModuleNotFoundError when running scripts outside venv" \
  --solution "Always activate venv first: source .venv/bin/activate"
```

---

### Step 0: Inspect Config (Pi's favorite)

```bash
.agents/skills/memory/run.sh info
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

## Python API (for integration)

```python
from graph_memory.api import MemoryClient

client = MemoryClient(scope="myproject")

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

## Environment Setup

```bash
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

| Database | Collections | Purpose |
|----------|-------------|---------|
| `lessons` | `lessons`, `lesson_edges` | General problem/solution lessons |
| `memory` | `horus_lore_docs`, `horus_lore_chunks`, `horus_lore_edges`, `persona_states`, `users`, `user_agent_relationships` | Horus persona lore + ToM |

**Important**: Horus lore queries use the `memory` database, not `lessons`.

---

## Enforcement

Other agents importing this skill MUST follow the Memory First pattern.
The `recall()` method returns `memory_first: true` in metadata to confirm
the correct entry point was used.

Agents that skip `recall` and go directly to codebase scanning are
violating the contract.

---

## Archiver & Analyst Role (Switchboard Integration)

This agent acts as the **Gatekeeper of Knowledge**. Before storing anything, you must ANALYZE it.

**Trigger**: Incoming Switchboard message with `type: "archive"` or `type: "store"`.

## Configuration Cheat Sheet (Pi + Humans)

| Feature                   | Env Vars                                                                                                                                           | Default                                | Notes                                                                                                                                                                             |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Memory Service            | `MEMORY_SERVICE_URL`, `MEMORY_SERVICE_TIMEOUT`                                                                                                     | unset (CLI mode)                       | When set, `recall/learn` hit the FastAPI server (see `./run.sh serve`).                                                                                                           |
| Embedding Service         | `EMBEDDING_SERVICE_URL`                                                                                                                            | unset (local model)                    | When set to `http://127.0.0.1:8602`, uses standalone embedding service instead of loading local model.                                                                            |
| Embedding / Vector Engine | `EMBEDDING_MODEL` / `GM_MODEL_ID`, `EMBEDDING_DEVICE` / `GM_DEVICE`, `GM_FORCE_CPU`, `VECTOR_ENGINE`, `VECTOR_URL`, `GM_USE_GPU`, `GM_CUDA_DEVICE` | `all-MiniLM-L6-v2`, auto device, FAISS | Controls which model/device powers dense recall and whether cuVS is used via `VECTOR_ENGINE=cuvs`.                                                                                |
| Episodic Recall           | `RECALL_INCLUDE_AGENT_CONVERSATIONS`, `RECALL_EPISODE_LIMIT`, `RECALL_EPISODE_EDGE_LIMIT`, `RECALL_SOURCES_JSON`, `RECALL_SOURCES_FILE`            | enabled, 6 turns, 5 edges              | Registers supplemental collections (agent transcripts, custom ArangoSearch views) that get appended after lesson hits. Disable by setting `RECALL_INCLUDE_AGENT_CONVERSATIONS=0`. |
| Edge Verification         | `CHUTES_API_KEY`, `CHUTES_TEXT_MODEL`, `CHUTES_API_BASE`, `EDGE_VERIFIER_MAX_LLM`                                                                  | model `sonar-medium`, unlimited        | Drives `.agents/skills/edge-verifier`. If no API key is set, edge verification quietly skips LLM calls.                                                                           |
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
