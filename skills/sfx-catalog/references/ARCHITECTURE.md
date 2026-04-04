## Data Flow

### 1. Cataloging Workflow

```
User SFX files
    ↓
Audio Analysis (librosa)
    ↓
Content Classification (rule-based)
    ↓
Description Generation (LLM optional)
    ↓
JSON Manifest
    ↓
Memory Ingestion (ArangoDB)
    ↓
Searchable Catalog
```

### 2. Query Workflow

```
User/Agent Query
    ↓
Query Engine
    ├─► Strategy 1: Check memory (prior usage)
    ├─► Strategy 2: Semantic search (embeddings)
    └─► Strategy 3: Generate (if missing)
    ↓
Ranked Results
    ↓
User Selection
    ↓
Usage Recording (for learning)
```

### 3. Learning Workflow

```
Every SFX Use
    ↓
Record: project, scene, rationale
    ↓
Store in sfx_usage collection
    ↓
Build patterns over time
    ↓
Improve future recommendations
```

## Technology Stack

### Audio Processing

- **librosa** - Audio feature extraction
- **soundfile** - Audio I/O
- **scipy** - Signal processing
- **numpy** - Numerical operations

### Memory & Search

- **ArangoDB** - Graph database (via memory skill)
- **python-arango** - Database client
- **Embeddings** - Via [`embedding`](../embedding) skill

### Generation (Optional)

- **Stable Audio Open** - Text-to-audio generation
- **PyTorch** - ML framework

### CLI & UX

- **typer** - CLI framework
- **rich** - Terminal formatting
- **task-monitor** - Progress reporting

## Performance

### Cataloging

- **Single file**: 2-3 seconds (audio analysis + description)
- **166 files**: 5-10 minutes (parallel processing, 4 workers)

### Queries

- **Memory search**: <100ms (indexed ArangoDB)
- **Semantic search**: <200ms (pre-computed embeddings)
- **Total query time**: <500ms end-to-end

### Generation

- **Text-to-audio**: 30-60 seconds per 3-second clip
- **Cache lookup**: <50ms (check before generating)

## Storage Requirements

- **Library files**: ~166MB (existing MP3 files)
- **Metadata**: ~50MB (JSON + ArangoDB)
- **Embeddings**: ~2MB (166 × 384 dimensions)
- **Generated SFX**: ~1GB over time
- **Total**: ~1.2GB

## Dependencies

### Required

- Python 3.11+
- ArangoDB (existing memory system)
- librosa, soundfile, scipy, numpy
- [`memory`](../memory) skill
- [`embedding`](../embedding) skill

### Optional

- [`scillm`](../scillm) skill (for LLM descriptions)
- Stable Audio Open (for generation)
- GPU with 8GB+ VRAM (accelerates generation)

## Configuration

Environment variables (optional, has defaults):

```bash
# Memory system
export MEMORY_ROOT="$HOME/workspace/experiments/memory"
export ARANGO_HOST="127.0.0.1"
export ARANGO_PORT="8529"

# SFX catalog data
export SFX_DATA_DIR="$HOME/.pi/sfx-catalog"

# LLM for descriptions (optional)
export SFX_LLM_MODEL="qwen2.5-coder:7b"
export SFX_LLM_PROVIDER="ollama"

# Audio generation (optional)
export STABLE_AUDIO_DEVICE="cuda:0"  # or "cpu"
```

## Installation

```bash
cd .pi/skills/sfx-catalog

# Install dependencies
uv sync

# Run sanity checks
./sanity/run_all.sh

# Verify memory connection
./run.sh status
```

See [EXAMPLES.md](EXAMPLES.md) for detailed usage examples including cataloging, scene matching, usage recording, and SFX generation.

---

# Catalog the entire library
./run.sh catalog /mnt/storage12tb/media/sfx/ \
    --output library_manifest.json \
    --parallel 4

# Review manifest
cat library_manifest.json | jq '.items[0]'

# Ingest into memory
./run.sh ingest library_manifest.json

# Test search
./run.sh search "impact" --limit 3
```

### Example 2: Finding SFX for a Scene

```bash
# Search for thunder sounds
./run.sh search "deep rumbling thunder" \
    --categories ambient \
    --duration 3-8

# Preview top result (if ffplay/mpv installed)
./run.sh search "thunder" --play-top
```

### Example 3: Recording Usage

```bash
# After selecting SFX for a scene
./run.sh record-usage \
    --sfx-id sfx_abc123 \
    --project "Storm Chaser" \
    --scene "EXT. FIELD - Dark clouds gather, distant thunder" \
    --timestamp 12.5 \
    --rationale "Sets ominous mood, foreshadows the storm"
```

### Example 4: Memory First Pattern

```bash
# Working on a new tense scene
./run.sh recall-usage "tense interior entrance quiet footsteps"

# Returns SFX used successfully in similar scenes:
# Result 1: footsteps_hardwood_slow.mp3 (used in "Dark Horizon" INT. APARTMENT)
#   Rationale: "Built tension perfectly during cautious entrance"
#   Score: 0.87
```

### Example 5: Generating Missing SFX

```bash
# Library doesn't have "sci-fi computer beep"
./run.sh generate "futuristic computer beep, clean, short" \
    --duration 0.5 \
    --ingest

# Generated SFX is now searchable:
./run.sh search "computer beep"
```

# Run all sanity checks
./sanity/run_all.sh

# Individual checks
./sanity/test_audio_analysis.sh   # Verify librosa
./sanity/test_memory.sh           # Verify ArangoDB
./sanity/test_search.sh           # Verify queries work

# Unit tests
uv run pytest tests/

# Integration tests
uv run pytest tests/integration/
```

# Check if ArangoDB is running
systemctl status arangodb3

# Verify memory skill works
cd ../memory
./run.sh status
```

### "No module named 'librosa'"

```bash
# Reinstall dependencies
uv sync --reinstall
```

### "Search returns no results"

```bash
# Check if catalog was ingested
./run.sh status

# Re-ingest if needed
./run.sh ingest library_manifest.json
```

### "Generation is too slow"

```bash
# Check if using GPU
./run.sh status --verbose

# Use shorter duration or lower quality
./run.sh generate "thunder" --duration 2.0 --steps 50
```
