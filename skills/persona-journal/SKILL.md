---
name: persona-journal
description: >
  Generate daily journal entries for personas. Creates human-like blog entries
  influenced by time/place, mood, personal life, and historical events specific
  to each persona's era. Integrates with /memory for storage and /taxonomy for
  multi-hop graph traversal.
allowed-tools: [Bash, Read, Write]
triggers:
  - persona journal
  - daily blog
  - generate journal
  - persona blog
  - write blog
metadata:
  short-description: Daily persona journal generation with temporal awareness
  author: "Horus"
  version: "0.1.0"

provides:
  - persona-journal
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - persona-simulation
  - content-creation
---

# persona-journal

Generate daily journal entries for all personas. Each entry is influenced by:
- **Temporal setting**: Personas live in THEIR time period (1956 persona experiences 1956, not 2026)
- **Personal life**: Pets, children, spouse, travel, war, work
- **Mood state**: Time of day, day of week, season, recent interactions
- **Non-sequential memory**: Semantic recall + random surfacing of old memories
- **Historical events**: Date-specific events from the persona's era via `/dogpile`

Based on Pennebaker's expressive writing research - journals should be messy, variable, sometimes boring, sometimes raw.

## Quick Start

```bash
cd .pi/skills/persona-journal

# Generate journals for all personas
./run.sh generate

# Generate for a specific persona
./run.sh generate --persona "Werner Herzog"

# Preview without storing (dry run)
./run.sh generate --dry-run

# Get current mood for a persona
./run.sh mood "Werner Herzog"

# Register nightly job with scheduler
./run.sh schedule

# List recent journal entries
./run.sh list --days 7
```

## Commands

### `generate` - Create Journal Entries

```bash
./run.sh generate [OPTIONS]

Options:
  --dry-run              Preview without storing to database
  --persona <name>       Generate for specific persona only
```

Generates journal entries for all personas (or specified persona) and stores them in ArangoDB with Federated Taxonomy tags for multi-hop retrieval.

### `mood` - Query Persona Mood

```bash
./run.sh mood <persona_name> [OPTIONS]

Options:
  --for-response         Format for injection into persona responses
```

Returns the current emotional state based on the most recent journal entry. Use this before generating persona responses to color them with current mood.

### `schedule` - Register Nightly Job

```bash
./run.sh schedule
```

Registers the journal generator with `/scheduler` to run at 3:00 AM daily.

### `list` - View Recent Journals

```bash
./run.sh list [OPTIONS]

Options:
  --persona <name>       Filter by persona
  --days <n>             Number of days to show (default: 7)
```

## Temporal Awareness

**CRUCIAL: A persona lives in THEIR time period, not ours.**

| Persona Era | Journal Date | Events Searched |
|-------------|--------------|-----------------|
| 2026 AD     | February 10  | "news February 10 2026" |
| 1956 AD     | February 10  | "what happened on February 10 1956" |
| 667 BC      | February     | "events in 667 BC" (broader, less docs) |

The persona's `temporal_setting` in their profile defines their reality:

```yaml
temporal_setting:
  year: 1956
  era: AD
  location: Los Angeles, California
```

## Personal Life Context

Personas have personal lives that influence their journals:

```yaml
personal_life:
  spouse: "Martha"
  children: ["Thomas (8)", "Sarah (5)"]
  pets: ["Max the German Shepherd"]
  current_situation: "traveling for work"
  relationship_dynamics: "tense marriage, close with children"
  typical_activities: ["reading", "walking the dog", "teaching"]
```

These details are woven into journal entries naturally.

## Journal Entry Styles

Based on mood and random chance, entries vary:

| Style | When | Example |
|-------|------|---------|
| `mundane` | Satisfied, low energy | "Made eggs. Read the paper. Nothing special." |
| `scattered` | Anxious, tired | "Called mom... need to finish the report... why did I say that to..." |
| `intense` | High emotion | Raw emotional processing, honest and messy |
| `brief` | Any mood | "Too tired. Going to bed." |
| `reflective` | Hopeful, calm | Gentle processing of the day's meaning |
| `venting` | Frustrated | Rambling complaint, unresolved |

## Memory Retrieval

Journals use non-sequential memory access (like humans):

1. **Rolling window**: Recent 7-day entries for continuity
2. **Semantic recall**: Older entries with similar mood/bridges
3. **Random surfacing**: 30% chance of random old memory popping up

This creates journals that reference events from months ago mixed with today.

## Taxonomy Integration

Each journal is tagged with Federated Taxonomy for multi-hop traversal:

```json
{
  "bridges": {
    "Fragility": 0.7,
    "Resilience": 0.3
  },
  "collection": "behavioral",
  "behavioral_tags": {
    "function": "Regulation",
    "domain": "Social",
    "thematic_weight": "Stress",
    "emotional_intensity": "High"
  }
}
```

**emotional_intensity** (Low, Moderate, High, Extreme) affects weight in multi-hop traversal - high intensity entries have stronger influence on persona responses.

## Storage

Journals are stored in ArangoDB collection `persona_journals`:

```json
{
  "persona": "Werner Herzog",
  "date": "2026-02-10",
  "mood": "contemplative",
  "energy_label": "moderate",
  "imagined_experiences": "...",
  "reflection": "...",
  "taxonomy": {...},
  "bridges": {...}
}
```

Graph edges are created to `taxonomy_bridges` and `personas` collections for multi-hop traversal.

## Memory Integration (memory_integration.py)

Cross-session memory persistence via `common.memory_client` with taxonomy bridge tagging.

### Pre-hook: `recall_recent_journals(persona_id, k=5)`
Recalls recent journal entries from memory for continuity — mood arcs, recurring themes, unresolved emotional threads.

### Post-hook: `learn_journal_entry(persona_id, date, mood, topics, key_events, ...)`
Learns journal snapshot after generation — mood, topics, key events, and reflections with taxonomy bridge tags.

### Bridge Keywords
| Bridge | Keywords |
|--------|----------|
| Precision | clarity, insight, understanding, realization |
| Resilience | growth, healing, strength, recovery, hope |
| Fragility | worry, fear, uncertainty, loneliness, anxiety |
| Loyalty | connection, friendship, trust, love, family |
| Stealth | secret, hidden, unspoken, suppressed |

Tags: `["persona_journal", persona_id] + bridges`

## Integration with Other Skills

| Skill | Relationship |
|-------|--------------|
| `/memory` | Stores journals in ArangoDB, queries for context |
| `/taxonomy` | Tags journals for multi-hop retrieval |
| `/dogpile` | Fetches historical events for persona's era |
| `/scheduler` | Runs nightly at 3 AM |
| `/create-persona` | Provides persona profiles with temporal_setting |

## Environment

| Variable | Purpose |
|----------|---------|
| `CHUTES_API_KEY` | LLM API for journal generation |
| `ARANGO_HOST` | ArangoDB connection |
| `ARANGO_DB` | Database name (default: horus) |

## Pennebaker Research Notes

Based on James Pennebaker's expressive writing research:
- 15-20 minute sessions
- Unpolished, messy entries
- Variable length (sometimes 2 sentences, sometimes pages)
- Emotional catharsis without resolution
- Stream-of-consciousness, not edited prose

The goal is emotional processing, not audience entertainment.
