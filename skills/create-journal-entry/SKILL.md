---
name: create-journal-entry
description: >
  Nightly journal entry creation for all personas. Wraps persona-journal generation
  with dream pipeline integration -- journal entries feed into create-movie dream
  residue and dreams feed back into future journals.
allowed-tools: [Bash, Read, Write]
triggers:
  - create journal entry
  - create journal
  - nightly journal
  - journal entry
  - generate journal entry
metadata:
  short-description: Nightly persona journal generation with dream pipeline integration
  author: "Horus"
  version: "1.0.0"

provides:
  - create-journal-entry
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - persona-simulation
  - content-creation
---

# create-journal-entry

Nightly journal entry creation for all personas. This skill bridges two systems:

1. **persona-journal** -- Generates mood-aware journal entries from daily interactions
2. **create-movie dream** -- Consumes journal entries as dream "day residue"

## Pipeline Position

```
2:00 AM  monitor-personas     (check persona sources)
3:00 AM  create-journal-entry (THIS SKILL - generate journals)
3:30 AM  create-movie dream   (dreams draw from journal entries as residue)
4:00 AM  assistant harvest    (extract escalations as training data)
5:00 AM  episodic-archiver    (archive sessions)
```

## Quick Start

```bash
cd .pi/skills/create-journal-entry

# Generate journal entries for all personas
./run.sh generate

# Generate for a specific persona
./run.sh generate --persona "Werner Herzog"

# Preview without storing (dry run)
./run.sh generate --dry-run

# Get current mood for a persona
./run.sh mood "Werner Herzog"

# List recent journal entries
./run.sh list --days 7

# Register nightly job with scheduler
./run.sh schedule
```

## Commands

### `generate` -- Create Journal Entries

```bash
./run.sh generate [OPTIONS]

Options:
  --dry-run              Preview without storing to database
  --persona <name>       Generate for specific persona only
```

Generates journal entries for all personas and stores them in ArangoDB.
Each entry includes mood state, imagined experiences, historical events,
taxonomy tags, and dream-pipeline metadata.

### `mood` -- Query Persona Mood

```bash
./run.sh mood <persona_name> [OPTIONS]

Options:
  --for-response         Format for injection into persona responses
```

### `list` -- View Recent Journals

```bash
./run.sh list [OPTIONS]

Options:
  --persona <name>       Filter by persona
  --days <n>             Number of days to show (default: 7)
```

### `schedule` -- Register Nightly Job

```bash
./run.sh schedule
```

Registers with `/scheduler` to run at 3:00 AM daily.

## Dream Pipeline Integration

Journal entries serve as **day residue** for the dream pipeline:

1. Journal entries are stored in ArangoDB (`persona_journals` collection)
2. `create-movie dream` queries journals via memory scopes during `fetch_day_residue()`
3. Dream motifs stored in `horus-dreams` scope feed back into future journal mood calculations

### Residue Sources from Journals

| Journal Field | Dream Residue Type | Example |
|---------------|--------------------|---------|
| `mood` | Emotional Tone | "contemplative" colors dream atmosphere |
| `reflection` | Unresolved Tension | Incomplete thoughts become dream threads |
| `imagined_experiences` | Personal Narrative | Daily fantasies seed surreal scenes |
| `key_events` | Event Anchors | Real interactions become dream imagery |

## Integration with Other Skills

| Skill | Relationship |
|-------|-------------|
| `/persona-journal` | Core implementation (this skill wraps it) |
| `/memory` | Stores journals in ArangoDB, queries for context |
| `/create-movie` | Dream pipeline consumes journal entries as residue |
| `/taxonomy` | Tags journals for multi-hop retrieval |
| `/dogpile` | Fetches historical events for persona's era |
| `/scheduler` | Runs nightly at 3 AM |
| `/episodic-archiver` | Provides daily interaction episodes |
| `/converse` | Uses mood context to color persona responses |

## Environment

| Variable | Purpose |
|----------|---------|
| `CHUTES_API_KEY` | LLM API for journal generation |
| `ARANGO_HOST` | ArangoDB connection |
| `ARANGO_DB` | Database name (default: horus) |
