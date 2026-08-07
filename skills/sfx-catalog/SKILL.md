---
name: sfx-catalog
description: >
  Sound effects management for Horus's filmmaking pipeline. Catalogs audio files
  with acoustic analysis, provides semantic search via memory integration, tracks
  usage patterns, and generates missing SFX. Makes sound effects discoverable,
  reusable, and learnable through the Memory First pattern.
allowed-tools: [Bash, Read, Write]
triggers:
  - catalog sfx
  - search sound effects
  - find sfx
  - sound effect library
  - audio library catalog
  - sfx search
  - record sfx usage
  - generate sound effect
metadata:
  short-description: Sound effects cataloging, search, and learning system
  version: "0.1.0"
  author: "Horus"

provides:
  - sfx-catalog
composes: [task-monitor]
disciplines:
  - voice-audio
  - content-creation
---

# sfx-catalog

Professional sound effects cataloging and management system for Horus's filmmaking pipeline.

> **Mission**: Make the right sound effect available at the right time, learning from every use.

## Quick Start

```bash
cd .pi/skills/sfx-catalog

# Catalog your SFX library
./run.sh catalog /mnt/storage12tb/media/sfx/ --output library.json

# Ingest into memory
./run.sh ingest library.json

# Search for sound effects
./run.sh search "door creak"

# Check system status
./run.sh status
```

## Problem Statement

Horus has a professional library of 166 studio-quality 3D sound effects, but they're numbered generically:

- `01-pro_studio_library-3d_sound_effect_1.mp3`
- `02-pro_studio_library-3d_sound_effect_2.mp3`
- ...

**Challenges:**

1. **Not searchable** - Generic filenames, no metadata
2. **Not reusable** - Can't remember which sounds work for which scenes
3. **Not learnable** - No pattern recognition across projects

**Solution**: The sfx-catalog system makes sound effects **discoverable, reusable, and learnable**.

## Core Features

### 1. Audio Analysis

Extracts technical characteristics from MP3 files:

- Duration, frequency profile, envelope (ADSR)
- Loudness metrics, harmonic content
- Automatic categorization (impact, ambient, foley, etc.)

### 2. Semantic Search

Natural language queries powered by memory integration:

```bash
./run.sh search "deep ominous thunder"
# Returns ranked results with similarity scores
```

### 3. Memory First

Learns from prior usage to improve recommendations:

```bash
./run.sh recall-usage "tense apartment entrance"
# Returns SFX successfully used in similar scenes before
```

### 4. Usage Tracking

Records context for every SFX selection:

```bash
./run.sh record-usage \
    --sfx-id abc123 \
    --project "Dark Horizon" \
    --scene "INT. APARTMENT - Sarah enters cautiously" \
    --rationale "Adds tension to entrance"
```

### 5. On-Demand Generation

Creates missing sound effects via AI when library lacks options:

```bash
./run.sh generate "metallic door slam" --duration 2.5 --ingest
```

## Integration Points

### [`create-movie`](../create-movie/SKILL.md)

Automatically selects and applies SFX during movie generation:

```python
# In create-movie workflow
from sfx_catalog.query_engine import SFXQueryEngine

engine = SFXQueryEngine(scope="horus_lore")

# Memory First: Check for prior usage
sfx = engine.recall_usage(scene_description)

# Fallback: Semantic search
if not sfx:
    sfx = engine.search(query, categories, duration_range)

# Record for future learning
engine.record_usage(sfx_id, project, scene, timestamp, rationale)
```

### [`create-storyboard`](../create-storyboard/SKILL.md)

Suggests sound effects during storyboard planning:

```python
# During storyboard phase
suggestions = suggest_sfx_for_shot(shot)
# Returns natural language recommendations with alternatives
```

## Architecture

High-level system design:

```
┌─────────────────┐
│ 166 MP3 Files   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│ Audio Analyzer  │────►│ Content Class.   │
│ (librosa)       │     │ (rule-based)     │
└─────────────────┘     └────────┬─────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │ Metadata Gen.    │
                        │ (LLM-assisted)   │
                        └────────┬─────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │ JSON Manifest    │
                        └────────┬─────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────┐
│          ArangoDB Memory                │
│  ┌────────────┐  ┌────────────────┐    │
│  │sfx_library │  │  sfx_usage     │    │
│  │(catalog)   │  │  (tracking)    │    │
│  └────────────┘  └────────────────┘    │
│  ┌────────────┐                         │
│  │sfx_generated                         │
│  │(cache)     │                         │
│  └────────────┘                         │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Query Engine    │ ◄──── create-movie, create-storyboard
│ (multi-strategy)│
└─────────────────┘
```

**Deep Dive**: See [`ARCHITECTURE.md`](references/ARCHITECTURE.md) for detailed component specifications.

## Memory Schema

SFX data is stored in ArangoDB with three main collections:

### `sfx_library` - Sound Effect Catalog

```json
{
  "_key": "sfx_abc123",
  "file_path": "/mnt/storage12tb/media/sfx/...",
  "description": "Deep, punchy impact with quick attack",
  "categories": ["impact", "low_frequency"],
  "audio_features": {
    "duration_seconds": 2.34,
    "envelope": {...},
    "frequency_profile": {...}
  },
  "embedding": [...],
  "usage_count": 5
}
```

### `sfx_usage` - Usage History

```json
{
  "sfx_id": "sfx_library/sfx_abc123",
  "project_name": "Dark Horizon",
  "scene_description": "INT. APARTMENT - Tense entrance",
  "timestamp_in_scene": 2.5,
  "rationale": "Adds atmosphere and tension"
}
```

### `sfx_generated` - Generation Cache

```json
{
  "prompt": "metallic door creak",
  "file_path": "/mnt/.../generated/door_creak.mp3",
  "reuse_count": 3,
  "user_approved": true
}
```

**Deep Dive**: See [`MEMORY_SCHEMA.md`](MEMORY_SCHEMA.md) for complete schema, indices, and query patterns.

## CLI Commands

### Core Workflow

```bash
# 1. Catalog audio files
./run.sh catalog <directory> --output manifest.json

# 2. Ingest into memory
./run.sh ingest manifest.json

# 3. Search catalog
./run.sh search "explosion boom" --categories impact --duration 2-5

# 4. Check system status
./run.sh status
```

### Advanced Operations

```bash
# Record usage after selection
./run.sh record-usage \
    --sfx-id abc123 \
    --project "Dark Horizon" \
    --scene "INT. WAREHOUSE - Explosion" \
    --timestamp 5.2

# Recall prior usage (Memory First)
./run.sh recall-usage "warehouse explosion scene"

# Find similar sounds
./run.sh similar sfx_abc123 --threshold 0.80

# Generate missing SFX
./run.sh generate "deep rumbling thunder" --duration 4.0 --ingest

# View usage statistics
./run.sh stats --type categories
```

**Full Reference**: See [`API.md`](API.md) for complete command documentation and Python API.

## Python API

For programmatic integration:

```python
from sfx_catalog import SFXQueryEngine

engine = SFXQueryEngine(scope="horus_lore")

# Memory First pattern
prior_usage = engine.recall_usage(
    scene_description="tense entrance scene",
    threshold=0.7
)

# Semantic search with filters
results = engine.search(
    query="door creak",
    categories=["foley"],
    duration_range=(1.0, 3.0),
    k=5
)

# Record usage for learning
engine.record_usage(
    sfx_id="sfx_abc123",
    project_name="Dark Horizon",
    scene_description="INT. APARTMENT - Sarah enters",
    timestamp_in_scene=2.5,
    rationale="Perfect tension builder"
)

# Generate if needed
generated = engine.generate_sfx(
    prompt="metallic door slam",
    duration=2.0,
    check_cache=True,  # Avoid duplicate generation
    ingest=True        # Add to catalog
)
```


See [EXAMPLES.md](references/EXAMPLES.md) for detailed usage examples including cataloging, scene matching, usage recording, and SFX generation.

See [ARCHITECTURE.md](references/ARCHITECTURE.md) for data flow diagrams, technology stack, performance benchmarks, storage requirements, and configuration.
