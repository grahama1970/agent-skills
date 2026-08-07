---
name: discover-talent
description: >
  Discover actors and reference talent via TMDB API with HMT taxonomy.
  Find actors by name, filmography, or bridge attributes.
  Used by create-cast for character reference discovery.
triggers:
  - discover talent
  - find actors
  - actor search
  - reference actors
  - casting reference
  - similar actors
  - who looks like
allowed-tools:
  - Bash
  - Python
metadata:
  short-description: "Actor/talent discovery via TMDB + Taxonomy"

provides:
  - discover-talent
composes: [task-monitor]
disciplines:
  - research-retrieval
  - content-creation
---

# Discover Talent Skill

Find actors and reference talent for casting in the Horus movie pipeline.

## Quick Start

```bash
cd .pi/skills/discover-talent

# Search actors by name
./run.sh search "Florence Pugh"

# Get actor's filmography
./run.sh filmography "Florence Pugh"

# Get cast of a movie
./run.sh by-movie "Oppenheimer"

# Find actors with bridge attributes
./run.sh bridge Corruption

# Find similar actors
./run.sh similar "Florence Pugh"

# Get profile images
./run.sh images "Florence Pugh"

# Check API connectivity
./run.sh check
```

## Discovery Services

| Service | API | Use For |
|---------|-----|---------|
| **TMDB** | Free API key | Actor search, filmography, images, similar people |

TMDB API key required. Get one free at: https://www.themoviedb.org/settings/api

## Commands

### Search Actors

```bash
./run.sh search "<name>" [--limit 10] [--json]
```

Search for actors by name. Returns:
- Actor name, popularity, known for department
- Profile image URL
- Top known-for movies

### Actor Filmography

```bash
./run.sh filmography "<name>" [--limit 10] [--department Acting] [--json]
```

Get an actor's complete filmography:
- Movies they've acted in (default)
- Movies they've directed (with `--department Directing`)
- Sorted by popularity

### Cast by Movie

```bash
./run.sh by-movie "<movie>" [--limit 10] [--json]
```

Get the cast of a specific movie:
- All actors in the movie
- Their character names
- Profile images for reference

### Search by Bridge

```bash
./run.sh bridge <attribute> [--limit 10] [--json]
```

Search for actors appearing in bridge-genre films:

| Bridge | Actor Types |
|--------|-------------|
| Precision | Technical thriller actors (heist, legal, procedural) |
| Resilience | Epic/war film actors (survival, historical) |
| Fragility | Drama/romance actors (indie, arthouse) |
| Corruption | Noir/horror actors (crime, psychological) |
| Loyalty | Period drama actors (family, western, military) |
| Stealth | Mystery/espionage actors (slow burn, conspiracy) |

### Similar Actors

```bash
./run.sh similar "<name>" [--limit 10] [--json]
```

Find actors similar to a given actor based on:
- Shared genre appearances
- Similar filmography patterns
- TMDB's "similar" algorithm

### Profile Images

```bash
./run.sh images "<name>" [--limit 5] [--json]
```

Get multiple profile images for an actor:
- Various angles and lighting
- Useful for identity pack reference

### Check API

```bash
./run.sh check
```

Test connectivity to TMDB API.

## Integration with create-cast

This skill is called by create-cast during Round 2 (Reference Discovery):

```
create-cast Round 2:
├── Extract character specs from script
├── For each character:
│   ├── Call discover-talent with character traits
│   ├── Find matching reference actors
│   └── Build mood board of references
└── Present options for selection
```

Example integration:
```bash
# create-cast calls:
./run.sh bridge Corruption --json | jq '.results[:3]'
# Returns: Actors known for noir/psychological roles

./run.sh similar "Florence Pugh" --json
# Returns: Actors with similar filmography/type
```

## Taxonomy Integration

All JSON output includes taxonomy metadata for cross-collection graph traversal:

```json
{
  "results": [...],
  "count": 5,
  "taxonomy": {
    "bridge_tags": ["Corruption", "Stealth"],
    "collection_tags": {
      "domain": "Chaos",
      "function": "Revelation"
    },
    "confidence": 0.75,
    "worth_remembering": true
  }
}
```

This enables queries like:
- "Find actors matching the Corruption theme of this scene"
- "Actors who've worked in Resilience-type films"

## Configuration

Environment variables:

```bash
TMDB_API_KEY=xxx    # Required: TMDB API key
```

## Rate Limits

| Service | Limit | Implementation |
|---------|-------|----------------|
| TMDB | ~40 req/10s | 0.25s minimum interval |

## Example Casting Queries

```bash
# "Who could play a determined protagonist?"
./run.sh bridge Resilience --limit 10

# "Actors similar to Florence Pugh for young lead"
./run.sh similar "Florence Pugh"

# "Dark, morally complex villain actors"
./run.sh bridge Corruption --limit 10

# "Who was in Blade Runner 2049?" (for reference)
./run.sh by-movie "Blade Runner 2049"

# "Get reference images for casting board"
./run.sh images "Ana de Armas" --limit 5 --json
```

## Output Formats

All commands support `--json` for agent-parseable output with taxonomy:

```json
{
  "results": [
    {
      "id": 1245,
      "name": "Florence Pugh",
      "known_for_department": "Acting",
      "popularity": 89.5,
      "profile_url": "https://image.tmdb.org/t/p/w500/xxx.jpg",
      "known_for": [
        {"title": "Oppenheimer", "year": "2023"},
        {"title": "Midsommar", "year": "2019"}
      ],
      "bridge_attributes": ["Fragility", "Corruption"]
    }
  ],
  "count": 1,
  "taxonomy": {
    "bridge_tags": ["Fragility", "Corruption"],
    "collection_tags": {"domain": "Chaos", "function": "Revelation"},
    "confidence": 0.75,
    "worth_remembering": true
  }
}
```

## Pipeline Integration

```
discover-talent → create-cast → create-image → identity packs
      ↓                ↓              ↓              ↓
  Find reference   Build spec    Generate look   Veo reference
  actors           with refs     from refs       images
```
