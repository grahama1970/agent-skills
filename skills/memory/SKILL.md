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
ARANGO_DB=lessons
ARANGO_USER=root
ARANGO_PASS=your_password

# Optional for LLM edge verification
CHUTES_API_BASE=...
CHUTES_API_KEY=...

# Optional: Embedding Service (Recommended)
EMBEDDING_SERVICE_URL=http://127.0.0.1:8602
```

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
