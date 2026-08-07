---
name: create-movie
description: >
  Orchestrated movie creation for Horus persona. Guides through phases:
  Research → Script → Build Tools → Generate → Assemble. Uses Docker-isolated
  coding environment, free/open-source tools only, with full memory integration.
allowed-tools: [Bash, Read, Write, Task, WebFetch, WebSearch]
triggers:
  - create movie
  - make movie
  - make film
  - create film
  - horus filmmaking
  - horus movie
  - create mockumentary
  - create short film
  - create music video
  - vibe coding movie
  - ai movie creation
  - study filmmaking
  - learn cinematography
  - horus study
  - horus learn filmmaking
  - create dream
  - dream generate
  - nightly dream
  - persona dream
metadata:
  short-description: "Orchestrated movie creation (Research → Script → Build → Generate → Assemble)"
  author: "Horus"
  version: "0.1.0"

provides:
  - create-movie
composes:
  - memory
  - create-image
  - dogpile
  - assess
  - task-monitor
disciplines:
  - content-creation
  - agentic-orchestration
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# create-movie

Orchestrated movie creation for Horus persona. Creates mockumentaries, short films, music videos, and educational content through a phased workflow.

## Philosophy

> "AI isn't the artist, it's the amplifier" - Nobody & The Computer

Horus uses AI to turn imagination into audiovisual reality. He doesn't just use pre-built tools - he writes code to create his own tools.

## Phases

```
HARDWARE CHECK → RESEARCH → SCRIPT → CASTING → EXPERT REVIEW → GENERATE → ASSEMBLE → LEARN
```

**Note:** BUILD TOOLS is optional and only triggered when custom effects are needed.

### Phase 0: Hardware Detection (Automatic)

Before any generation, the orchestrator automatically detects hardware via `/ops-workstation`:

```bash
# Automatic hardware check on startup
./run.sh create "prompt"
# → Calls /ops-workstation gpu to detect VRAM
# → Calls /ops-workstation memory to detect RAM
# → Auto-selects optimal model variant
```

**Auto-Selection Logic:**

| Detected VRAM | Model Selected | Settings |
|---------------|----------------|----------|
| ≥24GB | LTX-2 19B FP8 | 720p/1080p, audio on, batch=1 |
| 16-23GB | LTX-2 19B FP4 | 720p only, audio on, batch=1 |
| 12-15GB | LTX-2 Distilled 2B | 720p, audio optional, batch=1 |
| <12GB | **RunPod suggested** | Prompts to use `/ops-runpod` |

**RAM-Based Optimizations:**

| Detected RAM | Optimization |
|--------------|--------------|
| ≥128GB | Weight streaming enabled (offload to RAM) |
| 64-127GB | Partial offloading |
| <64GB | No offloading, strict VRAM limits |

**Override Auto-Detection:**
```bash
# Force specific model variant
./run.sh create "prompt" --model ltx2-fp4
./run.sh create "prompt" --model ltx2-distilled
./run.sh create "prompt" --runpod  # Force cloud generation
```

### Phase 1: Research (Library-First)
1. **Check Horus's Library First:**
   - `horus-filmmaking` scope (past techniques, learnings)
   - `horus_lore` scope (YouTube transcripts, film analysis)
   - Ingested movies with emotion tags
   - Episodic archive (past filmmaking sessions)
2. **Search for New Resources:**
   - `/ingest-movie search` for films to watch
   - `/ingest-youtube search` for tutorials
3. **Deep Web Research:**
   - `/dogpile` for comprehensive multi-source search
   - `/surf` for specific tutorials/references

### Phase 2: Script (via /create-story)
- Integrates with `/create-story` skill for screenplay generation
- Uses Chutes models (chimera, qwen, deepseek-r1) for creative writing
- Parses INT./EXT. headings, dialogue, action, audio cues
- Outputs structured scene breakdown with visual descriptions

**Format Options:**
- `screenplay` (default) - Standard INT./EXT. scene headings
- `mockumentary` - Interview segments with talking heads + B-roll
- `reconstruction` - Historical recreation with narrator framing

### Phase 2.5: Casting (via /create-cast)
- Multi-round collaborative character casting
- Extracts characters from screenplay via script analysis
- Optional reference actor discovery via `/discover-talent` (TMDB)
- Generates identity packs: front, 3/4, full-body reference images
- Voice casting from existing TTS models or queues training
- Bridge attributes extracted via Federated Taxonomy

**Output:**
```
characters/
├── casting_session.json
├── SARAH/
│   ├── character_bible.yaml
│   └── identity_pack/
│       ├── front.png
│       ├── three_quarter.png
│       └── full_body.png
└── voice_assignments.yaml
```

### Phase 2.7: Expert Review (NON-NEGOTIABLE)

**When a creative team has multiple personas**, this phase enforces a feedback loop before generation:

```
1. DIRECTOR creates vision (shot list, style notes)
2. TECHNICAL EXPERT reviews for AI video execution
   - e.g., Dan Kieft for Kling, video model specialist for Veo
3. EXPERT sends formal notes to DIRECTOR
   - Technical limitations, proposed changes, questions
4. DIRECTOR approves, revises, or escalates
5. BOTH sign off before generation proceeds
```

**Required Documents:**
| Document | Purpose |
|----------|---------|
| `{EXPERT}_REVIEW.md` | Technical review with recommendations |
| `{EXPERT}_TO_{DIRECTOR}_FEEDBACK.md` | Formal notes requiring director decision |
| `{DIRECTOR}_APPROVAL.md` | Director sign-off on technical changes |
| `*_V2_APPROVED.md` | Final approved instructions for generation |

**Expert Personas (queryable via /memory):**
- **Dan Kieft** (scope: `dan-kieft`) - Kling AI, multi-shot prompting, character consistency
- **Video model specialists** - Add via `/ingest-youtube` + `/memory learn`

**Workflow:**
```bash
# 1. Create initial instructions
# (output: KLING_INSTRUCTIONS_V1.md)

# 2. Query expert persona
./run.sh recall --q "multi-shot prompting" --scope dan-kieft

# 3. Generate expert review
# (output: DAN_KIEFT_REVIEW.md)

# 4. Send to director for approval
# (output: DAN_TO_WILSON_FEEDBACK.md)

# 5. Director approves
# (output: WILSON_APPROVAL.md)

# 6. Final approved instructions
# (output: KLING_INSTRUCTIONS_V2_APPROVED.md)

# 7. ONLY NOW proceed to generation
```

**Skip Conditions:**
- Single-persona projects (no creative team)
- `--skip-expert-review` flag (use with caution)

### Phase 3: Build Tools (Optional)
- Write code in Docker-isolated sandbox
- Create custom tools for specific effects
- Iterate on approaches

### Phase 4: Generate
- Use ComfyUI, Stable Diffusion for images
- Use **auto-selected video model** based on hardware (LTX-2 FP8/FP4/Distilled)
- Use Whisper, IndexTTS2 for audio
- If hardware insufficient, automatically suggests `/ops-runpod`

### Phase 5: Assemble
- Combine assets with FFmpeg
- Output MP4 video or interactive HTML

### Phase 6: Learn
- Store successful techniques in /memory
- Remember what worked for future movies

## Quick Start

```bash
cd .pi/skills/create-movie

# Full orchestrated workflow (recommended)
./run.sh create "A 30-second film about discovering colors"

# With options
./run.sh create "film noir detective" \
    --duration 60 \
    --style "high contrast, shadows, venetian blinds" \
    --format mp4 \
    --work-dir ./noir_project

# Individual phases (for manual control)
./run.sh research "film noir lighting techniques"
./run.sh script --from-research research.json --duration 30 --use-create-story
./run.sh build-tools --script script.json
./run.sh generate --tools ./tools --script script.json --style "cinematic"
./run.sh assemble --assets ./assets --output movie.mp4 --format mp4
./run.sh learn --project-dir ./movie_project
```

## CLI Commands

### create
Full orchestrated workflow through all phases.
```bash
./run.sh create PROMPT [OPTIONS]
  --output, -o       Output file (default: movie.mp4)
  --work-dir, -w     Working directory (default: ./movie_project)
  --duration, -d     Target duration in seconds (default: 30)
  --style, -s        Visual style (e.g., 'cinematic', 'film noir')
  --format, -f       Output format: mp4 or html (default: mp4)
  --store-learnings  Store learnings in memory (default: true)
  --skip-research    Skip research phase if research.json exists
  --skip-casting     Skip casting phase (no identity packs)
```

### research
Library-first research: checks Horus's memory and ingested content before external search.
```bash
./run.sh research TOPIC [OPTIONS]
  --output, -o       Output file (default: research.json)
  --skip-external    Only search library, skip external sources
```

### script
Generate screenplay with scene breakdown. Integrates with `/create-story`.
```bash
./run.sh script [OPTIONS]
  --from-research, -r  Research JSON file (required)
  --prompt, -p         Override topic from research
  --duration, -d       Target duration in seconds
  --use-create-story   Use /create-story skill for screenplay
  --model, -m          LLM model (default: chimera)
  --output, -o         Output file (default: script.json)
```

### build-tools
Generate custom tools in Docker sandbox.
```bash
./run.sh build-tools [OPTIONS]
  --script, -s       Script JSON file (required)
  --output-dir, -o   Output directory (default: ./tools)
  --skip-docker      Use host instead of Docker sandbox
```

### generate
Create images, video, and audio assets.
```bash
./run.sh generate [OPTIONS]
  --tools, -t        Tools directory (default: ./tools)
  --script, -s       Script JSON file (required)
  --output-dir, -o   Assets output directory (default: ./assets)
  --style            Visual style to apply
```

### assemble
Combine assets into final output.
```bash
./run.sh assemble [OPTIONS]
  --assets, -a       Assets directory (required)
  --output, -o       Output file/directory (required)
  --format, -f       Output format: mp4 or html (default: mp4)
  --fps              Frames per second for MP4 (default: 24)
```

### learn
Store filmmaking insights in memory after a project.
```bash
./run.sh learn [OPTIONS]
  --project-dir, -p  Project directory (required)
  --scope            Memory scope (default: horus-filmmaking)
  --dry-run          Show learnings without storing
```

### study
Pre-phase: Learn filmmaking topics BEFORE creating movies. Targeted /dogpile with internal (memory) + external (web) search, then stores via `/memory learn`.
```bash
./run.sh study TOPIC [OPTIONS]
  --scope            Memory scope (default: horus-filmmaking)
  --deep/--quick     Deep research (dogpile) vs quick (YouTube search)
  --list-topics      Show suggested filmmaking topics

# Examples:
./run.sh study "cinematography lighting techniques" --deep
./run.sh study "camera framing composition" --deep
./run.sh study --list-topics
```

### study-all
Comprehensive learning session - studies all core filmmaking topics.
```bash
./run.sh study-all [OPTIONS]
  --scope            Memory scope (default: horus-filmmaking)
```

## Output Formats

### MP4 Video
Standard video file, playable anywhere.

### Interactive HTML
Web-based experience with:
- Frame-by-frame navigation
- Audio controls
- Scene metadata viewer

## Shot Specification (HorusShotSpec v0.1)

HorusShotSpec is a YAML-based shot specification format that replaces KSML for video generation.

### Schema Overview

```yaml
shot_id: "ACT1_SC02_SHOT03"
prompt:
  text: "A tense noir interrogation in a dim room. Slow dolly push toward suspect."
  negative: "text overlays, watermarks, shaky camera"
duration_s: 8                    # Valid: 4, 8, 16 seconds
aspect_ratio: "16:9"             # Valid: 16:9, 9:16, 1:1
resolution: "1080p"              # Valid: 720p, 1080p
references:
  subject_images:
    - path: "./assets/detective.png"
      weight: 0.7
controls:
  seed: 42
  safety: "default"
renderer:
  name: "veo"
  model: "veo-3.1-generate-preview"
metadata:
  scene: "SC02"
  act: "ACT1"
  sequence_order: 3
```

### Compilation

The `shot_compiler` module validates and compiles YAML to Veo API JSON:

```python
from core.shot_compiler import compile_yaml_to_veo_json

veo_request = compile_yaml_to_veo_json(yaml_content)
# → Returns dict ready for Veo API
```

### Validation Rules

| Field | Constraint |
|-------|------------|
| `duration_s` | Must be 4, 8, or 16 seconds |
| `aspect_ratio` | Must be 16:9, 9:16, or 1:1 |
| `references.subject_images` | Max 6 images |
| `references.*.weight` | 0.0 to 1.0 |
| `prompt.text` | Max 4000 characters |

### Migration from KSML

> **DEPRECATED**: KSML is deprecated in favor of HorusShotSpec YAML.
> See `docs/KSML_TO_YAML_MIGRATION.md` for migration guide.

**Quick comparison:**

| Feature | KSML (deprecated) | HorusShotSpec (recommended) |
|---------|-------------------|----------------------------|
| Renderer | Kling | Veo (or any) |
| Schema | Kling-specific | Renderer-neutral |
| Validation | Manual | Built-in constraints |
| Compilation | Export only | YAML → Veo JSON |


See [MODELS.md](references/MODELS.md) for the video model selection guide, VRAM requirements, camera controls, WAN 2.2, and performance expectations.

See [EXAMPLES.md](references/EXAMPLES.md) for workflow patterns, multi-model collaboration, and example sessions.

See [REFERENCE.md](references/REFERENCE.md) for available skills, free/open-source tools, memory integration, and dependencies.
