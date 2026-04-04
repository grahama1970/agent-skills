# SFX Catalog API Specification

## Overview

The SFX Catalog provides both CLI and Python APIs for sound effect management. All operations follow the skill conventions established in [`.pi/skills/CONVENTIONS.md`](../CONVENTIONS.md).

## Integration from create-movie

**MVP Pattern**: Simple query-based integration with graceful fallback.

```python
# In create-movie skill
import sys
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path.home() / ".pi" / "skills" / "sfx-catalog"))

from sfx_catalog import SFXQueryEngine

def get_sfx_for_scene(scene_description: str, duration: float = None):
    """Query SFX catalog for scene audio.

    Args:
        scene_description: Text description of audio need
        duration: Optional target duration in seconds

    Returns:
        Path to SFX file, or None if not found (graceful)
    """
    engine = SFXQueryEngine(scope="memory")  # Using "memory" database

    try:
        # Simple keyword search
        results = engine.search(
            query=scene_description,
            k=1
        )

        if results:
            return results[0]["filepath"]
        else:
            # Graceful fallback: video proceeds without SFX
            print(f"[INFO] No SFX found for '{scene_description}'")
            return None

    except Exception as e:
        # System unavailable: proceed silently
        print(f"[WARN] SFX catalog unavailable: {e}")
        return None

# Usage example
sfx_path = get_sfx_for_scene("ambient sound")
if sfx_path:
    add_audio_to_video(sfx_path)
# If None, video continues without audio (graceful)
```

**Key Points**:

- Query returns empty list if no matches → graceful
- Exception handling ensures video pipeline doesn't break
- SFX is optional enhancement, not blocker
- No Memory First pattern in MVP (Phase 2 feature)

---

## CLI Interface

### Entry Point

```bash
cd .pi/skills/sfx-catalog
./run.sh <command> [options]
```

All commands support `--help` for detailed usage.

---

## Commands

### `catalog` - Analyze and Catalog SFX Files

Analyze audio files and generate metadata manifest.

```bash
./run.sh catalog <directory> [OPTIONS]

Arguments:
  directory              Path to SFX directory (required)

Options:
  -o, --output PATH      Output manifest file (default: sfx_manifest.json)
  -p, --parallel INT     Parallel workers (default: 4)
  -r, --recursive        Scan directory recursively (default: false)
  --model NAME           LLM model for descriptions (default: local)
  --skip-existing        Skip files already in manifest
  --dry-run              Show what would be cataloged without writing

Examples:
  # Catalog entire library
  ./run.sh catalog /mnt/storage12tb/media/sfx/ \
      --output library_manifest.json \
      --parallel 4

  # Dry run to see what would be processed
  ./run.sh catalog /path/to/sfx/ --dry-run

  # Resume interrupted catalog
  ./run.sh catalog /path/to/sfx/ --skip-existing
```

**Output**: JSON manifest with audio features, categories, descriptions for each file.

**Progress**: Reports to [`task-monitor`](../task-monitor/SKILL.md) for long-running operations.

---

### `ingest` - Import Manifest into Memory

Ingest cataloged SFX into ArangoDB memory system.

```bash
./run.sh ingest <manifest> [OPTIONS]

Arguments:
  manifest               Path to manifest JSON file (required)

Options:
  --scope TEXT           Memory scope (default: horus_lore)
  --batch-size INT       Batch size for ingestion (default: 50)
  --compute-similarity   Compute similarity edges (slow)
  --dry-run              Validate without inserting

Examples:
  # Standard ingestion
  ./run.sh ingest sfx_manifest.json

  # With similarity graph computation
  ./run.sh ingest sfx_manifest.json --compute-similarity

  # Test ingestion without writing
  ./run.sh ingest sfx_manifest.json --dry-run
```

**Process**:

1. Validate manifest structure
2. Insert into `sfx_library` collection
3. Generate embeddings for semantic search
4. Optionally compute similarity edges
5. Update indices

---

### `search` - Query SFX Catalog

Search for sound effects using natural language or structured filters.

```bash
./run.sh search <query> [OPTIONS]

Arguments:
  query                  Natural language search query (required)

Options:
  -c, --categories LIST  Filter by categories (comma-separated)
  -d, --duration RANGE   Duration range in seconds (e.g., "1-3", "2.5-")
  -k, --limit INT        Number of results (default: 5)
  --threshold FLOAT      Similarity threshold 0-1 (default: 0.3)
  --source TEXT          Filter by source: library|generated|all (default: all)
  --format TEXT          Output format: table|json|paths (default: table)
  --play-top             Play top result (requires ffplay/mpv)

Examples:
  # Simple semantic search
  ./run.sh search "door creak"

  # With category filter
  ./run.sh search "explosion" --categories impact --duration 2-5

  # JSON output for scripting
  ./run.sh search "footsteps" --format json --limit 10

  # Quick preview
  ./run.sh search "thunder" --play-top
```

**Output**: Ranked list of matching SFX with scores and metadata.

---

### `record-usage` - Track SFX Usage

Record when/where a sound effect was used for learning.

```bash
./run.sh record-usage [OPTIONS]

Options:
  --sfx-id TEXT          SFX library ID (required)
  --sfx-path PATH        Or path to SFX file (auto-resolves ID)
  --project TEXT         Project name (required)
  --scene TEXT           Scene description (required)
  --timestamp FLOAT      Timestamp in scene seconds (required)
  --rationale TEXT       Why this SFX was chosen (optional)
  --shot INT             Shot number (optional)
  --mood TEXT            Scene mood (optional)
  --alternatives LIST    IDs of alternatives considered (comma-separated)
  --rating INT           User rating 1-5 (optional)

Examples:
  # Record usage with rationale
  ./run.sh record-usage \
      --sfx-id sfx_abc123 \
      --project "Dark Horizon" \
      --scene "INT. APARTMENT - Sarah enters cautiously" \
      --timestamp 2.5 \
      --rationale "Adds tension to entrance"

  # With path resolution
  ./run.sh record-usage \
      --sfx-path /mnt/storage12tb/media/sfx/thunder_deep.mp3 \
      --project "Storm Chaser" \
      --scene "EXT. FIELD - Lightning strikes" \
      --timestamp 5.2
```

**Effect**: Creates `sfx_usage` record in ArangoDB for future reference.

---

### `recall-usage` - Find Prior Usage

Query memory for SFX used in similar scenes (Memory First).

```bash
./run.sh recall-usage <scene_description> [OPTIONS]

Arguments:
  scene_description      Scene context to search for (required)

Options:
  -k, --limit INT        Number of results (default: 5)
  --threshold FLOAT      Similarity threshold 0-1 (default: 0.7)
  --project TEXT         Filter by project name
  --format TEXT          Output format: table|json (default: table)

Examples:
  # Find SFX used in tense scenes
  ./run.sh recall-usage "tense interior entrance"

  # Filter to specific project
  ./run.sh recall-usage "explosion" --project "Dark Horizon"

  # JSON output
  ./run.sh recall-usage "footsteps" --format json
```

**Output**: List of prior SFX uses with context, ranked by similarity.

---

### `generate` - Create New SFX

Generate sound effects using AI when library lacks suitable options.

```bash
./run.sh generate <prompt> [OPTIONS]

Arguments:
  prompt                 Text description of desired sound (required)

Options:
  -d, --duration FLOAT   Duration in seconds (default: 3.0)
  -o, --output PATH      Output file path (auto-generated if not provided)
  --model TEXT           Generation model (default: stable-audio-open)
  --steps INT            Generation steps (default: 100)
  --cfg-scale FLOAT      Classifier-free guidance (default: 7.0)
  --seed INT             Random seed for reproducibility
  --ingest               Auto-ingest into library after generation
  --check-cache          Check if similar generation exists (default: true)

Examples:
  # Generate and ingest
  ./run.sh generate "deep ominous thunder rumble" \
      --duration 4.0 \
      --ingest

  # With custom parameters
  ./run.sh generate "metallic door slam" \
      --duration 2.0 \
      --steps 150 \
      --cfg-scale 8.0 \
      --seed 42

  # Skip cache check (force generation)
  ./run.sh generate "explosion" --check-cache false
```

**Process**:

1. Check `sfx_generated` cache for similar prompts
2. If cached, return existing file
3. If not, generate via Stable Audio Open
4. Optionally ingest into library
5. Store in generation cache

---

### `similar` - Find Similar Sounds

Find acoustically/semantically similar SFX to a given file.

```bash
./run.sh similar <sfx_id_or_path> [OPTIONS]

Arguments:
  sfx_id_or_path         SFX ID or file path (required)

Options:
  -k, --limit INT        Number of results (default: 5)
  --threshold FLOAT      Similarity threshold 0-1 (default: 0.75)
  --method TEXT          Method: acoustic|semantic|both (default: both)
  --format TEXT          Output format: table|json (default: table)

Examples:
  # Find similar sounds
  ./run.sh similar sfx_abc123

  # By file path
  ./run.sh similar /mnt/storage12tb/media/sfx/thunder.mp3

  # Only acoustic similarity
  ./run.sh similar sfx_abc123 --method acoustic --threshold 0.85
```

**Output**: List of similar SFX with similarity scores.

---

### `stats` - Usage Statistics

Display usage statistics and analytics.

```bash
./run.sh stats [OPTIONS]

Options:
  --type TEXT            Stats type: overview|categories|projects|recent (default: overview)
  --project TEXT         Filter to specific project
  --days INT             Recent usage window in days (default: 30)
  --format TEXT          Output format: table|json|chart (default: table)

Examples:
  # Overall stats
  ./run.sh stats

  # Category breakdown
  ./run.sh stats --type categories

  # Project-specific
  ./run.sh stats --type projects --project "Dark Horizon"

  # Recent usage
  ./run.sh stats --type recent --days 7
```

**Output**: Analytics about SFX usage patterns.

---

### `status` - System Status

Check health of SFX catalog system.

```bash
./run.sh status [OPTIONS]

Options:
  --verbose              Show detailed diagnostics

Examples:
  ./run.sh status
  ./run.sh status --verbose
```

**Checks**:

- ArangoDB connection
- Memory service availability
- Collection sizes
- Index status
- Embedding service status

---

## Python API

For programmatic integration (e.g., from [`create-movie`](../create-movie) or [`create-storyboard`](../create-storyboard)).

### Installation

```python
# Add to skill's dependencies
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".pi" / "skills" / "sfx-catalog"))

from sfx_catalog import SFXCatalog, SFXQueryEngine, SFXMemoryBridge
```

### Core Classes

#### `SFXCatalog`

Main interface for cataloging operations.

```python
from sfx_catalog import SFXCatalog

catalog = SFXCatalog(scope="horus_lore")

# Catalog a directory
manifest = catalog.catalog_directory(
    directory="/mnt/storage12tb/media/sfx/",
    output="manifest.json",
    parallel=4
)

# Ingest into memory
catalog.ingest_manifest(
    manifest_path="manifest.json",
    compute_similarity=True
)
```

#### `SFXQueryEngine`

Multi-strategy search engine.

```python
from sfx_catalog.query_engine import SFXQueryEngine

engine = SFXQueryEngine(scope="horus_lore")

# Memory First: Check prior usage
prior_usage = engine.recall_usage(
    scene_description="tense apartment entrance",
    threshold=0.7,
    k=5
)

# Semantic search
results = engine.search(
    query="deep explosion",
    categories=["impact"],
    duration_range=(2.0, 5.0),
    k=5
)

# Find similar sounds
similar = engine.find_similar(
    sfx_id="sfx_abc123",
    threshold=0.80,
    method="both"  # acoustic + semantic
)

# Generate if not found
generated = engine.generate_sfx(
    prompt="metallic door creak",
    duration=2.5,
    check_cache=True,
    ingest=True
)
```

#### `SFXMemoryBridge`

Low-level memory operations.

```python
from sfx_catalog.memory_bridge import SFXMemoryBridge

bridge = SFXMemoryBridge(scope="horus_lore")

# Record usage
usage_id = bridge.record_usage(
    sfx_id="sfx_abc123",
    project_name="Dark Horizon",
    scene_description="INT. APARTMENT - Sarah enters",
    timestamp_in_scene=2.5,
    rationale="Adds tension",
    context={
        "mood": "tense",
        "lighting": "low_key"
    }
)

# Query prior usage
prior = bridge.recall_prior_usage(
    scene_description="mysterious entrance",
    threshold=0.7
)

# Search catalog
results = bridge.search_sfx(
    query="thunder",
    categories=["ambient", "impact"],
    duration_range=(2.0, 10.0),
    k=10
)

# Get statistics
stats = bridge.get_usage_stats(
    project_name="Dark Horizon"
)
```

---

## Integration Examples

### From create-movie

```python
# In create-movie/generate.py

from sfx_catalog.query_engine import SFXQueryEngine

def generate_scene_audio(scene: dict, script: dict):
    """Generate all audio for a scene."""
    engine = SFXQueryEngine(scope="horus_lore")

    # Parse audio cues from script
    for cue in scene.get("audio_cues", []):
        # Memory First: Check if we've used SFX for similar scenes
        prior_usage = engine.recall_usage(
            scene_description=f"{scene['description']} {cue['context']}",
            threshold=0.7
        )

        if prior_usage:
            # Reuse successful SFX
            sfx = prior_usage[0]
            print(f"✓ Reusing '{sfx['generated_name']}' from memory")
        else:
            # Search library
            results = engine.search(
                query=cue["description"],
                categories=cue.get("categories"),
                duration_range=(cue["duration"] * 0.8, cue["duration"] * 1.2)
            )

            if results:
                sfx = results[0]
            else:
                # Generate new SFX
                sfx = engine.generate_sfx(
                    prompt=cue["description"],
                    duration=cue["duration"],
                    ingest=True
                )

        # Record usage for future memory
        engine.record_usage(
            sfx_id=sfx["_key"],
            project_name=script["title"],
            scene_description=scene["description"],
            timestamp_in_scene=cue["timestamp"],
            rationale=cue.get("rationale", "Matched scene requirements")
        )

        # Add to audio track
        add_audio_at_timestamp(sfx["file_path"], cue["timestamp"])
```

### From create-storyboard

```python
# In create-storyboard/creative_suggestions.py

from sfx_catalog.query_engine import SFXQueryEngine

def suggest_sfx_for_shot(shot: dict) -> dict:
    """
    Suggest SFX during storyboarding phase.

    Returns creative suggestion for user review.
    """
    engine = SFXQueryEngine(scope="horus_lore")

    # Build context-aware query
    query = f"{shot['action']} {shot['mood']} {shot['camera_movement']}"

    # Search with broad categories
    results = engine.search(
        query=query,
        duration_range=(shot["duration"] * 0.5, shot["duration"] * 1.5),
        k=3
    )

    if not results:
        return {
            "suggestion": "No existing SFX found. We could generate one during production.",
            "generate_prompt": query
        }

    top_sfx = results[0]

    return {
        "suggestion": f"For this {shot['camera_movement']} shot, I'm thinking: '{top_sfx['description']}'",
        "rationale": f"The {shot['mood']} mood and {shot['action']} suggest this sound profile",
        "alternatives": [
            {"name": r["generated_name"], "description": r["description"]}
            for r in results[1:3]
        ],
        "preview_path": top_sfx["file_path"]
    }
```

---

## Data Structures

### SFX Search Result

```python
{
    "_key": "sfx_abc123",
    "_id": "sfx_library/sfx_abc123",
    "file_path": "/mnt/storage12tb/media/sfx/thunder.mp3",
    "description": "Deep ominous thunder rumble",
    "generated_name": "thunder_deep_ominous",
    "categories": ["ambient", "impact"],
    "use_cases": ["storm scene", "tension building"],
    "audio_features": {
        "duration_seconds": 3.5,
        "envelope_type": "sustained"
    },
    "usage_count": 5,
    "last_used": "2026-01-28T14:30:00Z",
    "score": 0.87,  # Search relevance score
    "source": "memory" | "semantic" | "generated"
}
```

### Usage Record

```python
{
    "_key": "usage_xyz789",
    "_id": "sfx_usage/usage_xyz789",
    "sfx_id": "sfx_library/sfx_abc123",
    "project_name": "Dark Horizon",
    "scene_description": "INT. APARTMENT - Tense entrance",
    "timestamp_in_scene": 2.5,
    "rationale": "Adds atmosphere and tension",
    "context": {
        "mood": "tense",
        "camera_movement": "dolly_in"
    },
    "user_feedback": {
        "rating": 5,
        "reused": true
    },
    "created_at": "2026-01-28T14:30:00Z"
}
```

---

## Error Handling

All API functions raise structured exceptions:

```python
from sfx_catalog.exceptions import (
    SFXNotFoundError,
    MemoryConnectionError,
    InvalidManifestError,
    GenerationError
)

try:
    results = engine.search("explosion")
except SFXNotFoundError:
    # No matching SFX found
    results = engine.generate_sfx("explosion", ingest=True)
except MemoryConnectionError as e:
    # ArangoDB not available
    logger.error(f"Memory unavailable: {e}")
    # Fallback to file-based search
except Exception as e:
    logger.exception("Unexpected error in SFX search")
```

---

## Environment Variables

```bash
# Memory root (where graph-memory is installed)
export MEMORY_ROOT="$HOME/workspace/experiments/memory"

# ArangoDB connection
export ARANGO_HOST="127.0.0.1"
export ARANGO_PORT="8529"
export ARANGO_DB="memory"
export ARANGO_USER="root"
export ARANGO_PASSWORD="..."

# SFX catalog data directory
export SFX_DATA_DIR="$HOME/.pi/sfx-catalog"

# LLM for description generation
export SFX_LLM_MODEL="qwen2.5-coder:7b"  # Local Ollama model
export SFX_LLM_PROVIDER="ollama"         # or "openai", "anthropic"

# Audio generation
export STABLE_AUDIO_MODEL="stabilityai/stable-audio-open-1.0"
export STABLE_AUDIO_DEVICE="cuda:0"      # or "cpu"
```

---

## Testing

### Sanity Checks

```bash
# Run all sanity checks
./sanity/run_all.sh

# Individual checks
./sanity/test_audio_analysis.sh    # Verify librosa installation
./sanity/test_memory.sh            # Verify ArangoDB connection
./sanity/test_search.sh            # Verify search functionality
./sanity/test_generation.sh        # Verify audio generation
```

### Unit Tests

```bash
# Run Python tests
uv run pytest tests/

# Specific test suites
uv run pytest tests/test_audio_analyzer.py
uv run pytest tests/test_query_engine.py
uv run pytest tests/test_memory_bridge.py
```

---

## Performance

### Typical Response Times

| Operation           | Time    | Notes                            |
| ------------------- | ------- | -------------------------------- |
| Catalog single file | 2-3s    | Audio analysis + LLM description |
| Catalog 166 files   | 5-10min | Parallel processing (4 workers)  |
| Memory search       | <100ms  | Indexed queries                  |
| Prior usage recall  | <150ms  | Semantic similarity              |
| Generate SFX        | 30-60s  | Depends on model/duration        |
| Record usage        | <50ms   | Simple DB insert                 |

### Batch Operations

For large-scale operations:

```python
# Batch catalog with progress reporting
from sfx_catalog.batch import batch_catalog

results = batch_catalog(
    directories=["/path1", "/path2"],
    parallel=8,
    report_to_monitor=True  # Integrates with task-monitor
)
```

---

## Next Steps

- See [`ARCHITECTURE.md`](ARCHITECTURE.md) for system design
- See [`MEMORY_SCHEMA.md`](MEMORY_SCHEMA.md) for database details
- See [`ROADMAP.md`](ROADMAP.md) for implementation plan
