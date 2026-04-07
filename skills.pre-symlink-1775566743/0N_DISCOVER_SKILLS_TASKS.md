# Task List: Discover Skills for Verb Consistency

## Summary

Create `discover-movies` and `discover-books` skills to match the existing `discover-music` pattern. This ensures verb consistency across the media consumption pipeline.

## CRITICAL: Taxonomy Integration Required

**The persona `/memory` system will NOT work unless all skills have consistent interconnected taxonomy.**

All discover skills MUST integrate with the Federated Taxonomy system from `/home/graham/workspace/experiments/memory/persona`. This enables:

1. **Bridge Attribute Mapping** - Map genres/tags to Bridge Attributes (Precision, Resilience, Fragility, Corruption, Loyalty, Stealth)
2. **Cross-Collection Traversal** - Enable queries like "movies similar to Siege of Terra lore" via shared bridges
3. **Taxonomy Output** - All JSON output must include taxonomy metadata for downstream skills

### Required Taxonomy Integration Pattern

```python
# Import from taxonomy skill (path: .pi/skills/taxonomy or /memory/.agents/skills/taxonomy)
from taxonomy import extract_taxonomy, BRIDGE_TAGS

# Bridge → Genre/Tag mappings (media-specific)
BRIDGE_TO_GENRES = {
    "Precision": [...],  # Calculated, methodical content
    "Resilience": [...], # Endurance, triumph content
    "Fragility": [...],  # Delicate, vulnerable content
    "Corruption": [...], # Dark, compromised content
    "Loyalty": [...],    # Honor, duty content
    "Stealth": [...],    # Hidden, subtle content
}

# All output MUST include taxonomy
def discover_output(items: list) -> dict:
    return {
        "results": items,
        "taxonomy": {
            "bridge_tags": [...],
            "collection_tags": {"domain": "...", "function": "..."},
            "confidence": 0.8,
            "worth_remembering": True
        }
    }
```

### Taxonomy Source Files

| File | Purpose |
|------|---------|
| `/memory/.agents/skills/taxonomy/taxonomy.py` | Core extraction functions |
| `/memory/.agents/skills/taxonomy/INTEGRATION.md` | Integration guide |
| `/memory/.agents/skills/review-music/src/taxonomy.py` | HMT bridge mappings (reference) |
| `/memory/persona/code/taxonomy_versioning.py` | Version/contradiction handling |

## Current State

| Verb | Music | Movie | Book |
|------|-------|-------|------|
| **discover** | ✓ `discover-music` | ✗ MISSING | ✗ MISSING |
| **ingest** | ✗ | ✓ `ingest-movie` | ✓ `ingest-book` |
| **consume** | ✓ `consume-music` | ✓ `consume-movie` | ✓ `consume-book` |
| **review** | ✓ `review-music` | ✗ (via dogpile) | ✗ (via dogpile) |

## Verb Semantics

- `discover-*` → Find NEW content externally (recommendations, similar, trending)
- `ingest-*` → Acquire/download content (Readarr, Radarr, NZBGeek)
- `consume-*` → Use/watch/read content with context
- `review-*` → Analyze and critique content

## Reference Implementation: discover-music

```
discover-music/
├── SKILL.md              # Skill documentation
├── run.sh                # CLI entry point
├── pyproject.toml        # Dependencies
├── sanity.sh             # Sanity test runner
├── sanity/
│   ├── musicbrainz.py    # API connectivity test
│   └── listenbrainz.py   # API connectivity test
├── src/
│   ├── __init__.py
│   ├── cli.py            # Typer CLI commands
│   ├── musicbrainz_client.py  # API client
│   └── listenbrainz_client.py # API client
└── tests/
    └── test_*.py         # Unit tests
```

**Commands pattern:**
- `similar <item>` - Find similar items
- `trending` - Get trending items
- `search-tag <tag>` - Search by genre/tag
- `fresh` - New releases
- `check` - API connectivity test

---

## Task 1: Create discover-movies skill

**Priority:** High
**Effort:** Medium (2-3 hours)

### APIs to Use

| API | Auth | Use For |
|-----|------|---------|
| **TMDB** | Free API key | Similar movies, trending, genres, recommendations |
| **Trakt** | OAuth (optional) | Personalized recommendations, watchlists |
| **Letterboxd** | Scraping (no API) | Lists, reviews, recommendations |

### Commands to Implement

```bash
./run.sh similar "There Will Be Blood"     # Find similar movies
./run.sh trending --range week             # Trending movies
./run.sh search-genre "psychological thriller"  # Search by genre
./run.sh by-director "Paul Thomas Anderson"    # Movies by director
./run.sh fresh                             # New releases
./run.sh recommendations                   # Based on consume-movie history
./run.sh check                             # API connectivity test
```

### Files to Create

```
discover-movies/
├── SKILL.md
├── run.sh
├── pyproject.toml
├── sanity.sh
├── sanity/
│   └── tmdb.py
├── src/
│   ├── __init__.py
│   ├── cli.py
│   └── tmdb_client.py
└── tests/
    └── test_tmdb.py
```

### Integration Points

- Output feeds into `ingest-movie` for acquisition
- Uses `consume-movie` history for personalized recommendations
- Can be invoked via `/dogpile movies`

### Taxonomy Integration (REQUIRED)

```python
# src/taxonomy.py - Bridge → Genre mappings
BRIDGE_TO_GENRES = {
    "Precision": ["thriller", "heist", "procedural", "legal", "documentary"],
    "Resilience": ["war", "epic", "survival", "sports", "biography"],
    "Fragility": ["drama", "romance", "indie", "arthouse", "coming-of-age"],
    "Corruption": ["noir", "crime", "psychological", "horror", "dystopian"],
    "Loyalty": ["family", "period drama", "historical", "western", "military"],
    "Stealth": ["mystery", "espionage", "slow burn", "neo-noir", "conspiracy"],
}
```

### Definition of Done

- [ ] `./run.sh similar "Dune"` returns 10+ similar movies
- [ ] `./run.sh trending` returns current trending movies
- [ ] `./run.sh bridge Corruption` returns matching movies by bridge attribute
- [ ] `./sanity.sh` passes (API connectivity)
- [ ] `--json` output includes `taxonomy` field with bridge_tags
- [ ] SKILL.md documents all commands including bridge search
- [ ] `src/taxonomy.py` contains BRIDGE_TO_GENRES mapping

---

## Task 2: Create discover-books skill

**Priority:** High
**Effort:** Medium (2-3 hours)

### APIs to Use

| API | Auth | Use For |
|-----|------|---------|
| **OpenLibrary** | Free (no key) | Book search, author works, subjects |
| **Google Books** | Free API key | Search, recommendations |
| **Goodreads** | Scraping (API deprecated) | Lists, recommendations |
| **StoryGraph** | Scraping (no API) | Mood-based recommendations |

### Commands to Implement

```bash
./run.sh similar "Dune"                    # Find similar books
./run.sh by-author "Frank Herbert"         # Books by author
./run.sh search-subject "science fiction"  # Search by subject
./run.sh trending                          # Popular/trending books
./run.sh fresh                             # New releases
./run.sh recommendations                   # Based on consume-book history
./run.sh check                             # API connectivity test
```

### Files to Create

```
discover-books/
├── SKILL.md
├── run.sh
├── pyproject.toml
├── sanity.sh
├── sanity/
│   └── openlibrary.py
├── src/
│   ├── __init__.py
│   ├── cli.py
│   └── openlibrary_client.py
└── tests/
    └── test_openlibrary.py
```

### Integration Points

- Output feeds into `ingest-book` (Readarr) for acquisition
- Uses `consume-book` history for personalized recommendations
- Can be invoked via `/dogpile books`

### Taxonomy Integration (REQUIRED)

```python
# src/taxonomy.py - Bridge → Subject mappings
BRIDGE_TO_SUBJECTS = {
    "Precision": ["hard sci-fi", "technical thriller", "procedural", "mathematics", "philosophy"],
    "Resilience": ["epic fantasy", "military fiction", "adventure", "survival", "heroic"],
    "Fragility": ["literary fiction", "poetry", "memoir", "psychological", "tragedy"],
    "Corruption": ["dark fantasy", "horror", "grimdark", "cosmic horror", "dystopian"],
    "Loyalty": ["historical fiction", "saga", "mythology", "war fiction", "family drama"],
    "Stealth": ["mystery", "espionage", "thriller", "psychological thriller", "noir"],
}
```

### Definition of Done

- [ ] `./run.sh similar "Dune"` returns 10+ similar books
- [ ] `./run.sh by-author "Frank Herbert"` returns author's works
- [ ] `./run.sh bridge Resilience` returns matching books by bridge attribute
- [ ] `./sanity.sh` passes (API connectivity)
- [ ] `--json` output includes `taxonomy` field with bridge_tags
- [ ] SKILL.md documents all commands including bridge search
- [ ] `src/taxonomy.py` contains BRIDGE_TO_SUBJECTS mapping

---

## Task 3: Update dogpile to invoke discover skills

**Priority:** Medium
**Effort:** Low (30 min)

### Changes Needed

1. Add `discover-movies` as a dogpile resource
2. Add `discover-books` as a dogpile resource
3. Route `/dogpile movies` to discover-movies
4. Route `/dogpile books` to discover-books

### Files to Modify

- `dogpile/resources/presets.yaml` - Add movie/book presets
- `dogpile/cli.py` or `dogpile_monolith.py` - Add routing

### Definition of Done

- [ ] `/dogpile movies "psychological thriller"` invokes discover-movies
- [ ] `/dogpile books "science fiction classics"` invokes discover-books

---

## Task 4: Cross-Collection Taxonomy Verification

**Priority:** High (required for /memory integration)
**Effort:** Medium (1 hour)

### Purpose

Verify that all discover skills produce consistent taxonomy output that enables multi-hop graph traversal across:
- `discover-music` → `review-music` → `consume-music`
- `discover-movies` → `ingest-movie` → `consume-movie`
- `discover-books` → `ingest-book` → `consume-book`

### Verification Tests

```bash
# Each skill must output taxonomy with bridge_tags
./discover-movies/run.sh similar "Blade Runner" --json | jq '.taxonomy.bridge_tags'
# Expected: ["Corruption", "Stealth"]

./discover-books/run.sh similar "Neuromancer" --json | jq '.taxonomy.bridge_tags'
# Expected: ["Corruption", "Precision"]

./discover-music/run.sh similar "Nine Inch Nails" --json | jq '.taxonomy.bridge_tags'
# Expected: ["Corruption"]
```

### Cross-Collection Query Test

```bash
# Query by bridge should find content across all media types
# This is the KEY test for /memory integration
./discover-movies/run.sh bridge Corruption --json > movies.json
./discover-books/run.sh bridge Corruption --json > books.json
./discover-music/run.sh bridge Corruption --json > music.json

# All should have consistent taxonomy.bridge_tags = ["Corruption"]
```

### Definition of Done

- [ ] All discover skills output `taxonomy.bridge_tags` in JSON mode
- [ ] Bridge searches work consistently: `./run.sh bridge <Bridge>`
- [ ] Cross-collection query test passes (same bridge returns related content)
- [ ] Taxonomy vocabulary validated against `/memory/.agents/skills/taxonomy/taxonomy.py`

---

## Task 5: Skills broadcast after completion

**Priority:** Required
**Effort:** Low (5 min)

After all skills are created and tested:

```bash
skills-broadcast push --from /home/graham/workspace/experiments/pi-mono/.pi/skills
```

### Definition of Done

- [ ] All agents (codex, claude, gemini, pi) have the new skills

---

## Environment Variables Needed

```bash
# discover-movies
TMDB_API_KEY=xxx              # Required for TMDB
TRAKT_CLIENT_ID=xxx           # Optional for Trakt

# discover-books
GOOGLE_BOOKS_API_KEY=xxx      # Optional for Google Books
```

## Notes

- OpenLibrary requires no API key (just rate limiting)
- TMDB free tier is generous (1000 req/day)
- All skills should respect rate limits (1-2 req/sec)
- Use `--json` flag for agent-parseable output
- Follow discover-music as the canonical implementation pattern
