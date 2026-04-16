# AGENTS.md - Operator Guide for create-score

## Overview

`create-score` generates scene-specific music using ACE-Step 1.5 via a Dockerized FastAPI service. It integrates with the Federated Taxonomy (HMT) for multi-hop graph traversal in `/memory`.

## Quick Start

```bash
cd .pi/skills/create-score

# Start service (first time may take 5-10 mins to download model)
./run.sh up

# Generate a simple score
./run.sh generate \
  --prompt "cinematic tension, building suspense" \
  --duration-s 30 \
  --out test.wav

# Generate with HMT bridge hints
./run.sh generate \
  --prompt "battle preparation" \
  --bridges Resilience,Precision \
  --episode Siege_of_Terra \
  --out battle.wav

# Stop service when done
./run.sh down
```

## Python API (for create-movie)

```python
import sys
sys.path.insert(0, ".pi/skills/create-score")

from create_score import generate_scene_score
from pathlib import Path

result = generate_scene_score(
    prompt="heroic theme, brass fanfare",
    duration_s=30,
    output_path=Path("./hero_theme.wav"),
    bridges=["Resilience"],
    episode="Siege_of_Terra",
    seed=42,
)

print(f"Generated: {result.output_path}")
print(f"Bridges: {result.hmt.bridge_attributes}")
```

## CLI Reference

### `./run.sh up`

Start the ACE-Step Docker service.

| Option | Description |
|--------|-------------|
| `--build` | Force rebuild Docker image |
| `--verbose` | Verbose logging |

### `./run.sh down`

Stop the ACE-Step Docker service.

### `./run.sh generate`

Generate scene music.

**Required:**
| Option | Description |
|--------|-------------|
| `--prompt` | Text prompt for generation |
| `--out` | Output file path |

**Generation:**
| Option | Default | Description |
|--------|---------|-------------|
| `--duration-s` | 30 | Duration in seconds (1-300) |
| `--steps` | 27 | Inference steps |
| `--seed` | -1 | Seed (-1 = random) |
| `--cfg-scale` | 4.0 | Guidance scale |
| `--format` | wav | Output format (wav/mp3/flac) |

**HMT:**
| Option | Description |
|--------|-------------|
| `--bridges` | Comma-separated bridges (Resilience,Precision) |
| `--episode` | Episode association |
| `--store-memory/--no-store-memory` | Store in /memory |

**Conditioning:**
| Option | Description |
|--------|-------------|
| `--reference-audio` | Reference for theme continuity |
| `--tags` | Genre/style tags |

## Bridge Attributes → Musical Keywords

| Bridge | Keywords Added to Prompt |
|--------|--------------------------|
| Precision | polyrhythmic, technical, algorithmic patterns |
| Resilience | triumphant, epic strings, powerful brass, heroic |
| Fragility | delicate, acoustic, tender piano, breaking |
| Corruption | industrial, distorted, harsh textures, oppressive |
| Loyalty | ceremonial, choral, sacred tones, anthemic |
| Stealth | ambient, drone, minimal, atmospheric pads |

## Episode → Bridge Mapping

| Episode | Bridges | Music Character |
|---------|---------|-----------------|
| Siege_of_Terra | Resilience, Fragility | Defiant, enduring |
| Davin_Corruption | Corruption | Dark, oppressive |
| Webway_Collapse | Fragility, Precision | Breaking, tragic |
| Mournival_Oath | Loyalty | Ceremonial, solemn |
| Iron_Cage | Precision, Resilience | Calculated, relentless |

## Docker Service

### Health Check

```bash
curl http://localhost:8015/healthz
# {"ok": true, "jobs_queued": 0, "jobs_total": 5}
```

### Manual API Access

```bash
# Submit generation
curl -X POST http://localhost:8015/generate \
  -F 'json={"prompt":"test prompt","duration_s":10}' \
  | jq .job_id

# Check status
curl http://localhost:8015/jobs/{job_id} | jq .

# Download output
curl http://localhost:8015/outputs/{filename} -o output.wav
```

### Logs

```bash
docker compose -f docker/compose.yml logs -f
```

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU VRAM | 16GB | 24GB (A5000) |
| System RAM | 32GB | 64GB |
| Disk | 50GB | 100GB |

## Troubleshooting

### Service won't start

```bash
# Check logs
docker compose -f docker/compose.yml logs --tail=100

# Check GPU
nvidia-smi

# Rebuild image
./run.sh up --build
```

### Generation times out

- Increase `--poll-timeout` (default: 900s)
- Reduce `--steps` for faster (lower quality) generation
- Check GPU memory with `nvidia-smi`

### Output too quiet/noisy

- Adjust `--cfg-scale` (higher = more prompt adherence)
- Try different prompts with more specific descriptors

## Task Monitor Integration

All generation jobs are automatically tracked via `/task-monitor`:

```bash
# View in TUI
cd .pi/skills/task-monitor
uv run python monitor.py tui --filter create-score

# Check state file
cat .pi/skills/create-score/score_task_state.json | jq .

# API (if running)
curl http://localhost:8765/tasks/create-score
```

State file location: `.pi/skills/create-score/score_task_state.json`

## Memory Integration

Generated scores are stored in `/memory` with scope `horus-filmmaking`:

```bash
# Recall by bridge
/memory recall --bridge Resilience --category music_score

# Recall by episode
/memory recall --episode Siege_of_Terra --category music_score
```

## Related Skills

| Skill | Use |
|-------|-----|
| `/create-movie` | Calls create-score per-scene |
| `/memory` | Stores scores with HMT taxonomy |
| `/taxonomy` | Provides bridge extraction |
| `/consume-music` | Searches existing music |
| `/discover-music` | Finds reference music |
