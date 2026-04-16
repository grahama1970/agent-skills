---
name: ask
description: >
  Zero cognitive-load learning and querying skill. Learn about a topic or persona (e.g., "Lisa Feldman Barrett")
  by discovering, ingesting, and extracting knowledge — or ask questions against what's been learned.
  Supports multi-hour deep learning with progress tracking, persona profiles, and nightly incremental updates.
  Uses Federated Taxonomy for multi-hop graph traversal across knowledge domains.
  Composes: dogpile, discover-books, ingest-youtube, fetcher, extractor, memory, taxonomy, task-monitor.
allowed-tools: [Bash, Read, Write]
triggers:
  - I want to learn about
  - I want to ask
  - ask about
  - learn about
  - /ask
  - teach me about
  - what does X say about
  - what does Sapolsky say
  - what does Barrett say
  - learn from
  - ask about embry
  - how does X skill work
  - what does the X skill do
  - is memory healthy
  - is X healthy
  - what skills provide
  - os health
  - os learn
metadata:
  short-description: Zero cognitive-load learning and querying for personas, topics, and OS internals
  author: "Horus"
  version: "0.6.0"

provides:
  - ask
  - os-knowledge
composes:
  - create-context
  - monitor-memory
  - monitor-skills
  - monitor-skill-health
  - monitor-security
  - monitor-sparta
  - monitor-personas
  - monitor-taxonomy
  - ops-workstation
  - ops-arango
  - ops-docker
  - ops-llm
  - ops-chutes
  - task-monitor
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# ask

Zero cognitive-load learning and querying interface. Five modes:

1. **Learn Mode** — Discover, ingest, and extract knowledge about a topic or persona
2. **Ask Mode** — Query accumulated knowledge with Federated Taxonomy multi-hop traversal
3. **Auto-Learn Mode** — Ask a question; if no knowledge exists, automatically learn then answer
4. **Nightly Mode** — Scheduled incremental updates to persona knowledge bases
5. **OS Mode** — Learn about and query embry-os internals, skills, packages, and runtime health

## Zero Cognitive Load for Project Agents

Project agents should just ask — the skill handles all discovery complexity:

```bash
# Project agent just asks a question
./run.sh ask "Lisa Feldman Barrett how might we improve our /memory system?" --auto-learn

# What happens automatically:
# 1. Memory check (existing knowledge?)
# 2. /dogpile deep research (Brave, Perplexity, ArXiv, YouTube, GitHub)
# 3. YouTube transcript ingestion (lectures, interviews)
# 4. Web content fetching (blogs, articles)
# 5. QRA extraction + Federated Taxonomy tagging
# 6. Memory storage with persona profile
# 7. Answer synthesis with multi-hop traversal
```

## Quick Start

```bash
cd .pi/skills/ask

# Learn about a persona (deep learning)
./run.sh learn "Lisa Feldman Barrett" --scope behavioral --depth deep

# Ask with auto-learn (discovers + ingests if no knowledge exists)
./run.sh ask "What does Sapolsky say about free will?" --scope behavioral --auto-learn

# Interactive mode (asks about learning preferences)
./run.sh learn "Robert Sapolsky" --scope behavioral --interactive

# Check learning progress (includes task-monitor state with ETA)
./run.sh status --scope behavioral

# Run nightly persona update
./run.sh nightly --scope behavioral
```

## Commands

### `ask` — Query Accumulated Knowledge

```bash
./run.sh ask <question> [options]

Options:
  --scope <scope>         Memory scope to query (default: "ask")
  --k <n>                 Number of results (default: 5)
  --bridges               Also traverse bridge attributes (multi-hop)
  --auto-learn            Auto-discover and learn if no knowledge found
  --collection <coll>     Taxonomy collection for auto-learn (default: behavioral)
  --consult-personas      Find and suggest relevant personas to consult
  --persona-scope <scope> Scope to search for personas (default: personas)
  --hybrid                Use hybrid RAG+QRA retrieval
  --raw                   Return raw memory results (no synthesis)
  --json                  JSON output
  --debug                 Enable debug logging
```

**Persona Routing:**

When `--consult-personas` is enabled, /ask uses Federated Taxonomy bridges to find
personas best suited to answer the question:

```bash
./run.sh ask "How should we improve visual hierarchy in the UI?" --consult-personas

# Output:
#   Suggested personas to consult:
#     - Paula Scher (Graphic Designer) [Precision]
#     - Don Norman (Cognitive Scientist) [Precision, Loyalty]
```

This enables cross-persona knowledge queries where Embry can automatically
identify that Paula Scher should be consulted for typography questions.

**Auto-Learn Flow:**
```
Question → Memory Recall → No results?
  YES → Learn Pipeline (dogpile → YouTube → web → QRA → store)
      → Re-query Memory → Return answer with multi-hop traversal
  NO  → Return answer directly with bridge connections
```

### `learn` — Discover and Ingest Knowledge

```bash
./run.sh learn <topic> [options]

Options:
  --scope <scope>         Memory scope (default: "ask")
  --collection <coll>     Taxonomy collection (lore, operational, sparta, behavioral)
  --depth <level>         Learning depth: quick (5-10min), standard (30-60min), deep (hours)
  -i, --interactive       Use /interview to ask about learning preferences
  --youtube <url>         Specific YouTube URL to ingest (repeatable)
  --books-only            Only discover and process books
  --youtube-only          Only process YouTube content
  --max-books <n>         Max books to discover (default: 5)
  --max-videos <n>        Max YouTube videos to process (default: 3)
  --dry-run               Preview what would be ingested without storing
  --debug                 Enable debug logging
```

**Learning Depths:**

| Depth | Time | Videos | Books | ArXiv | Use Case |
|-------|------|--------|-------|-------|----------|
| `quick` | 5-10 min | 3 | 0 | 0 | Quick overview, verify facts |
| `standard` | 30-60 min | 5 | 3 | 3 | Moderate understanding |
| `deep` | 2-6 hours | 10+ | 5 | 10 | Comprehensive persona building |

**Persona Detection:**
When the topic looks like a person's name (e.g., "Lisa Feldman Barrett", "Dr. Robert Sapolsky"),
the skill automatically:
- Stores a persona profile to memory
- Searches for additional lectures by the person
- Downloads books by/about the person
- Creates a queryable knowledge base

### `status` — Learning Progress

```bash
./run.sh status [options]

Options:
  --scope <scope>         Filter by scope
  --json                  JSON output
  --debug                 Enable debug logging
```

Shows:
- Total knowledge items in scope
- Persona profiles
- Q-R-A pairs count
- Last task-monitor state (steps, timing, stats, ETA)

### `nightly` — Scheduled Persona Updates

```bash
./run.sh nightly [options]

Options:
  --scope <scope>         Memory scope to update (default: ask)
  --persona <name>        Update a single persona by name
  --dry-run               Preview without storing
  --json                  Output summary as JSON
  --debug                 Enable debug logging
```

**Nightly Update Flow:**
1. Query memory for all stored persona profiles
2. For each persona, search for new content since last update
3. Ingest new YouTube videos, papers, news articles
4. Update persona profile with new sources
5. Report summary via task-monitor

### `os` — Query Embry-OS Internals

```bash
# Index OS knowledge (skills, packages, config)
./run.sh os learn --depth quick --dry-run
./run.sh os learn --depth standard

# Query OS knowledge
./run.sh os ask "what does the /dogpile skill do?"
./run.sh os ask "which skills provide memory?" --json

# Query runtime health
./run.sh os health "is memory healthy?"
./run.sh os health "check workstation" --subsystem workstation

# Classify query intent
./run.sh intent "how does the memory skill work?"
```

**OS Learn** crawls `.pi/skills/*/SKILL.md`, `packages/*/package.json`, `.pi/config.toml`,
and `.pi/extensions/*.ts`. Generates QRA triples tagged with `scope=os`, bridge attributes,
and source metadata (skill, package, config, extension).

**OS Health** dispatches to the relevant monitor/ops skill (e.g., `monitor-memory health --json`)
and combines runtime data with static knowledge from memory.

**Intent Classifier** routes queries through a 3-stage pipeline:
1. Memory cache (~1ms) — cached classifications
2. Rule-based heuristics (<5ms) — regex pattern matching
3. LLM fallback (1-5s) — scillm classification when uncertain

## Architecture

```
Agent: "Lisa Feldman Barrett how might we improve our memory system?"
                    │
                    ▼
            ┌──────────────┐
            │ Persona Detect│  ← Is this a person?
            └──────┬───────┘
                   │
            ┌──────┴───────┐
            │ Memory Recall │  ← Check what we already know
            └──────┬───────┘
                   │
              Items found?
              ┌────┴────┐
             YES        NO + --auto-learn
              │          │
              │    ┌─────┴──────────────────────────────────┐
              │    │ Learn Loop (multi-source, multi-hour)  │
              │    │                                         │
              │    │ 1. /dogpile (Brave + Perplexity + etc)  │
              │    │ 2. YouTube ingest (lectures, interviews)│
              │    │ 3. Web fetch (blogs, articles)          │
              │    │ 4. discover-books (OpenLibrary)         │
              │    │ 5. extractor --format qra               │
              │    │ 6. memory learn + persona profile       │
              │    │                                         │
              │    │ (tracked via task-monitor with ETA)     │
              │    └─────┬──────────────────────────────────┘
              │          │
              │    ┌─────┴──────┐
              │    │ Re-query   │
              │    └─────┬──────┘
              │          │
              └────┬─────┘
                   │
            ┌──────┴───────┐
            │  Synthesize  │  ← Combine results
            └──────┬───────┘
                   │
            ┌──────┴────────────────┐
            │ Federated Taxonomy    │  ← Multi-hop bridge traversal
            │ (Corruption, Precision,│
            │  Resilience, etc.)     │
            └───────────────────────┘
```

## Task-Monitor Integration

Every `learn` session registers with `/task-monitor`:

- **Registry**: `~/.pi/task-monitor/registry.json`
- **State file**: `.pi/skills/ask/ask_task_state.json` (atomic writes)
- **Steps tracked**: `memory_check → dogpile → ingest_youtube → fetch_web → extractor_qra → store`
- **Sub-steps**: Individual items within each step (e.g., each video URL)
- **ETA**: Estimated time remaining based on depth and progress
- **Stats**: books_discovered, youtube_ingested, web_fetched, qra_extracted, items_stored

```bash
# View real-time progress
cat .pi/skills/ask/ask_task_state.json | python3 -m json.tool

# Example state output:
{
  "completed": 3,
  "total": 6,
  "progress_pct": 55.0,
  "current_item": "ingest_youtube",
  "current_detail": "https://youtube.com/watch?v=...",
  "substep_current": 2,
  "substep_total": 5,
  "eta_seconds": 180.0,
  "eta_display": "~3 min remaining",
  "depth": "standard"
}

# Via task-monitor TUI
cd ~/.pi/skills/task-monitor
uv run python monitor.py tui --filter ask
```

## Federated Taxonomy Integration

Knowledge is tagged with bridge attributes for multi-hop graph traversal:

| Bridge | Meaning | Example Topics |
|--------|---------|----------------|
| Corruption | Moral decay, entropy | Power dynamics, institutional failure |
| Precision | Exactness, clarity | Scientific method, measurement |
| Resilience | Recovery, adaptation | Stress response, neuroplasticity |
| Fragility | Vulnerability | Trauma, system failure |
| Stealth | Hidden operations | Unconscious processes |

**Multi-hop Query Example:**
```
Query: "How does stress affect decision-making?"
          │
          ├── Direct hits: Stress research papers
          │
          └── Bridge traversal:
              ├── [Resilience] → Neuroplasticity studies
              ├── [Fragility] → Trauma responses
              └── [Corruption] → Decision biases under stress
```

## Memory Scopes

| Scope | Use |
|-------|-----|
| `behavioral` | Psychology, neuroscience, behavioral studies |
| `ask` | General learning (default) |
| Custom | Any scope name you provide |

## Environment

| Variable | Purpose |
|----------|---------|
| `ASK_DEFAULT_SCOPE` | Override default memory scope |
| `ASK_NIGHTLY_SCOPE` | Scope for nightly updates |
| `ASK_MAX_BOOKS` | Override default max books to discover |
| `ASK_MAX_VIDEOS` | Override default max videos |
| `ASK_DEBUG` | Enable debug logging (set to any value) |
| `TASK_MONITOR_URL` | Task-monitor API URL for remote push |

## Related Skills

| Skill | Relationship |
|-------|--------------|
| `/dogpile` | Primary discovery engine (Brave, Perplexity, ArXiv, YouTube, GitHub) |
| `/memory` | Knowledge storage and retrieval |
| `/discover-books` | Book discovery via OpenLibrary |
| `/ingest-youtube` | YouTube transcript extraction |
| `/fetcher` | Web content fetching |
| `/extractor` | Document extraction with QRA mode |
| `/taxonomy` | Federated Taxonomy tagging |
| `/interview` | Interactive preference gathering |
| `/task-monitor` | Progress tracking with ETA |
| `/scheduler` | Nightly update scheduling |
| `/prompt-lab` | Prompt optimization for scillm calls |

## Persona Profiles

When learning about a person, a persona profile is stored to memory:

```json
{
  "name": "Lisa Feldman Barrett",
  "scope": "behavioral",
  "sources": {
    "dogpile_sections": 5,
    "books": 3,
    "youtube": 8,
    "web": 4
  },
  "stats": {
    "qra_extracted": 45,
    "stored": 46
  },
  "last_updated": "2024-01-15T10:30:00"
}
```

Query a persona:
```bash
./run.sh ask "How does Barrett define emotions?" --scope behavioral --bridges
```

## Nightly Scheduling

To run nightly persona updates automatically, use the `/scheduler` skill or cron:

```bash
# Via scheduler skill
./path/to/scheduler/run.sh add ask-nightly \
  --command ".agent/skills/ask/run.sh nightly --scope behavioral" \
  --schedule "0 3 * * *"  # 3 AM daily

# Via cron
# Add to crontab -e:
# 0 3 * * * /path/to/.agent/skills/ask/run.sh nightly --scope behavioral >> /var/log/ask-nightly.log 2>&1
```
