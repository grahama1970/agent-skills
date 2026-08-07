---
name: create-score
description: >
  Generate scene-specific music using ACE-Step 1.5 via Dockerized FastAPI.
  Supports reference audio for theme continuity across scenes.
  Integrates with Federated Taxonomy (HMT) for multi-hop graph traversal in /memory.
allowed-tools: [Bash, Read, Write]
triggers:
  - create score
  - score scene
  - generate music
  - film score
  - ace step
  - scene music
  - soundtrack
metadata:
  short-description: "Scene music generation via ACE-Step (Docker + HMT)"
  author: "Horus"
  version: "0.1.0"

provides:
  - create-score
composes:
  - create-cast
  - create-storyboard
  - create-sound-design
  - create-story
  - task-monitor
disciplines:
  - content-creation
  - voice-audio
---

# create-score

Generate scene-specific music for films using ACE-Step 1.5 via a Dockerized FastAPI service. Designed to be called per-scene by `/create-movie`.

## Philosophy

Music scoring is the emotional backbone of film. This skill generates original music that matches scene context, using Federated Taxonomy (HMT) bridge attributes to ensure thematic coherence across scenes.

## Quick Start

```bash
cd .pi/skills/create-score

# Start the ACE-Step Docker service (persistent)
./run.sh up

# Generate a scene score
./run.sh generate \
  --prompt "cinematic tension, strings and low brass, building suspense" \
  --duration-s 30 \
  --seed 42 \
  --out scene_01.wav

# Generate with bridge hints (HMT-aware)
./run.sh generate \
  --prompt "battle preparation" \
  --bridges Resilience,Precision \
  --episode Siege_of_Terra \
  --duration-s 45 \
  --out battle_prep.wav

# Use reference audio for theme continuity
./run.sh generate \
  --prompt "same theme, higher intensity" \
  --reference-audio outputs/main_theme.wav \
  --duration-s 30 \
  --out scene_02.wav

# Stop the service when done
./run.sh down
```

## CLI Commands

### `up` - Start Docker Service

```bash
./run.sh up
```

Builds and starts the ACE-Step Docker service. Waits for health check before returning.

### `down` - Stop Docker Service

```bash
./run.sh down
```

Stops the ACE-Step Docker service.

### `generate` - Generate Scene Music

```bash
./run.sh generate [OPTIONS]
```

**Required:**
| Option | Description |
|--------|-------------|
| `--prompt` | Text prompt describing desired music |
| `--out` | Output file path |

**Generation:**
| Option | Default | Description |
|--------|---------|-------------|
| `--duration-s` | 30 | Duration in seconds (1-300) |
| `--steps` | 27 | Inference steps (more = higher quality, slower) |
| `--seed` | -1 | Seed for reproducibility (-1 = random) |
| `--cfg-scale` | 4.0 | Guidance scale (higher = more prompt adherence) |
| `--format` | wav | Output format: wav, mp3, flac |

**HMT Integration:**
| Option | Description |
|--------|-------------|
| `--bridges` | Comma-separated bridge attributes (Resilience,Corruption,etc.) |
| `--episode` | Episode association for memory storage |
| `--store-memory/--no-store-memory` | Store in /memory (default: true) |

**Conditioning:**
| Option | Description |
|--------|-------------|
| `--reference-audio` | Reference audio for style/theme continuity |
| `--tags` | Comma-separated genre/style tags |
| `--instrumental/--no-instrumental` | Instrumental only (default: true) |

## Python API

For integration with `/create-movie`:

```python
import sys
sys.path.insert(0, ".pi/skills/create-score")

from create_score import generate_scene_score
from pathlib import Path

result = generate_scene_score(
    prompt="battle preparation, epic strings, building tension",
    duration_s=30,
    output_path=Path("./outputs/battle_scene.wav"),
    bridges=["Resilience", "Precision"],
    episode="Siege_of_Terra",
    reference_audio=Path("./outputs/main_theme.wav"),
    seed=42,
    format="wav",
    store_memory=True,
)

print(result["output_path"])        # Path to generated audio
print(result["hmt"])                # Full HMT taxonomy
print(result["episode_association"]) # Episode link
```

### Return Value

```python
{
    "output_path": Path("outputs/battle_scene.wav"),
    "prompt": "battle preparation, epic strings, triumphant, heroic",  # augmented
    "seed": 42,
    "duration_s": 30.0,
    "hmt": {
        "bridge_attributes": ["Resilience", "Precision"],
        "collection_tags": {
            "domain": ["Orchestral_Epic"],
            "thematic_weight": ["Epic"],
            "function": ["Score"]
        },
        "tactical_tags": ["Score", "Amplify"],
        "episodic_associations": ["Siege_of_Terra"],
        "confidence": 0.85
    },
    "episode_association": "Siege_of_Terra"
}
```

## HMT Integration

This skill uses the Federated Taxonomy (HMT) to:

1. **Extract bridges from scene context** - Automatically detect thematic bridges from prompts
2. **Augment prompts** - Add bridge-appropriate musical keywords
3. **Tag output** - Generated scores include full HMT metadata
4. **Enable multi-hop retrieval** - Query scores by bridge, episode, or tactical use

### Bridge to Music Mapping

| Bridge | Musical Keywords |
|--------|------------------|
| **Precision** | polyrhythmic, technical, algorithmic patterns, complex |
| **Resilience** | triumphant, epic strings, powerful brass, heroic |
| **Fragility** | delicate, acoustic, tender piano, breaking |
| **Corruption** | industrial, distorted, harsh textures, oppressive |
| **Loyalty** | ceremonial, choral, sacred tones, anthemic |
| **Stealth** | ambient, drone, minimal, atmospheric pads |

### Episode Associations

| Episode | Primary Bridge | Music Character |
|---------|----------------|-----------------|
| Siege_of_Terra | Resilience | Defiant, enduring |
| Davin_Corruption | Corruption | Dark, oppressive |
| Webway_Collapse | Fragility | Breaking, tragic |
| Mournival_Oath | Loyalty | Ceremonial, solemn |
| Iron_Cage | Precision | Calculated, relentless |

## Reference Audio Continuity

For thematic coherence across scenes:

```bash
# Scene 1: Establish main theme
./run.sh generate \
  --prompt "heroic main theme, brass fanfare" \
  --duration-s 30 \
  --seed 42 \
  --out main_theme.wav

# Scene 2: Variation on theme
./run.sh generate \
  --prompt "same theme, quieter, strings only" \
  --reference-audio main_theme.wav \
  --duration-s 20 \
  --out scene_02.wav

# Scene 3: Climactic return
./run.sh generate \
  --prompt "theme returns, full orchestra, triumphant" \
  --reference-audio main_theme.wav \
  --duration-s 45 \
  --out climax.wav
```

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU VRAM | 16GB | 24GB (A5000/RTX 4090) |
| System RAM | 32GB | 64GB+ |
| Disk | 50GB | 100GB (model cache) |

### VRAM Usage

| Mode | VRAM | Quality |
|------|------|---------|
| FP8 | ~20GB | High |
| FP4 | ~12GB | Good |
| BF16 | ~40GB | Maximum (RunPod) |

## Task Monitor Integration

All generation jobs are automatically tracked via `/task-monitor`:

- **Registry**: Jobs register at `~/.pi/task-monitor/registry.json`
- **State File**: Progress written to `create-score/score_task_state.json`
- **API Push**: If `TASK_MONITOR_API` is set, pushes to HTTP API

### View Progress

```bash
# Via task-monitor TUI
cd .pi/skills/task-monitor
uv run python monitor.py tui --filter create-score

# Via API
curl http://localhost:8765/tasks/create-score
```

### Manual Tracking (Advanced)

```python
from create_score import ScoreMonitor

monitor = ScoreMonitor(prompt="battle theme", duration_s=30)
monitor.start_job(job_id="abc123", seed=42)
monitor.update_progress(state="generating", progress_pct=50)
monitor.complete_job(output_path=Path("output.wav"))
```

## Memory Integration

Generated scores are automatically stored in `/memory` with scope `horus-filmmaking`:

```bash
# Recall scores by bridge
/memory recall --bridge Resilience --category music_score

# Recall by episode
/memory recall --episode Siege_of_Terra --category music_score

# Multi-hop: Find lore documents linked to same bridges as a score
/memory traverse --from music_score --via bridge --to lore
```

## Docker Service

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ACE_STEP_PORT` | 8015 | Service port |
| `HF_TOKEN` | - | HuggingFace token (for gated models) |

### Health Check

```bash
curl http://localhost:8015/healthz
# {"ok": true}
```

### Manual API Access

```bash
# Submit generation
curl -X POST http://localhost:8015/generate \
  -F 'json={"prompt":"test","duration_s":10}' \
  | jq .job_id

# Poll status
curl http://localhost:8015/jobs/{job_id}

# Download output
curl http://localhost:8015/outputs/{filename} -o output.wav
```

## Dependencies

- Docker with GPU support (NVIDIA Container Toolkit)
- Python 3.11+
- uv (for dependency management)

## Related Skills

| Skill | Relationship |
|-------|--------------|
| `/create-movie` | Calls create-score per-scene |
| `/memory` | Stores scores with HMT taxonomy |
| `/taxonomy` | Provides bridge extraction |
| `/consume-music` | Searches existing music (not generated) |
| `/discover-music` | Finds reference music for inspiration |
