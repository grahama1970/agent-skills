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
metadata:
  short-description: "Orchestrated movie creation (Research → Script → Build → Generate → Assemble)"
  author: "Horus"
  version: "0.1.0"
---

# create-movie

Orchestrated movie creation for Horus persona. Creates mockumentaries, short films, music videos, and educational content through a phased workflow.

## Philosophy

> "AI isn't the artist, it's the amplifier" - Nobody & The Computer

Horus uses AI to turn imagination into audiovisual reality. He doesn't just use pre-built tools - he writes code to create his own tools.

## Phases

```
RESEARCH → SCRIPT → BUILD TOOLS → GENERATE → ASSEMBLE → LEARN
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

### Phase 3: Build Tools
- Write code in Docker-isolated sandbox
- Create custom tools for specific effects
- Iterate on approaches

### Phase 4: Generate
- Use ComfyUI, Stable Diffusion for images
- Use LTX-Video, Mochi for video clips
- Use Whisper, IndexTTS2 for audio

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

## Available Skills

Horus has access to all skills in `.pi/skills/`:

| Skill | Purpose in Movie Creation |
|-------|---------------------------|
| `/dogpile` | Deep research on techniques, references |
| `/surf` | Visit websites, tutorials, references |
| `/memory` | Recall prior techniques, store learnings |
| `/create-image` | Generate images for scenes |
| `/tts-train` | Horus's voice for narration |
| `/ingest-movie` | Ingest reference movies for style analysis |
| `/create-paper` | Write stories, scripts, creative content |
| `/episodic-archiver` | Archive movie creation sessions |
| `/anvil` | Debug and harden custom tools |
| `/ingest-book` | Search books for story inspiration |

## Free/Open-Source Tools

| Purpose | Tool |
|---------|------|
| Image Generation | Stable Diffusion (ComfyUI) |
| Video Generation | LTX-Video, Mochi 1 (AI motion video) |
| Video Processing | FFmpeg |
| Speech-to-Text | faster-whisper |
| Text-to-Speech | IndexTTS2 |

## Video Model Selection Guide

Choose video model based on your GPU VRAM and use case:

| VRAM | Recommended Models | Best For |
|------|-------------------|----------|
| 12GB (RTX 3060/4070) | LTX-Video, CogVideoX-2B | Quick iterations, pre-viz |
| 16GB (RTX 4080/A4000) | SVD, DynamiCrafter, Latte | Medium quality production |
| 24GB (RTX 4090/A5000) | Most models with optimization | High quality production |
| 40GB+ (A100/H100) | Full Mochi, Open-Sora 2.0 | Maximum quality |

### Model Characteristics

| Model | Speed | Quality | Best Use Case |
|-------|-------|---------|---------------|
| **LTX-Video** | Fastest | Medium | Rapid iteration, rough cuts |
| **Mochi 1** | Slow | High | Final renders, prompt adherence |
| **HunyuanVideo** | Medium | High | Production quality |
| **CogVideoX-5B** | Medium | High | General purpose |
| **Pyramid Flow** | Fast | Medium | Efficient workflows |

**Recommendation:** Use LTX-Video for drafts/pre-viz, Mochi or HunyuanVideo for final output.

## Memory Integration

After each movie, stores:
- Successful prompts
- Working tool code
- Technique insights
- Concept relationships

Scope: `horus-filmmaking`

## Workflow Patterns (from Nobody & The Computer)

### Multi-Model Collaboration
Different AI models handle different creative aspects, inspired by "Bach x Coltrane x Kuti x Takemitsu":
- **Model A (Claude)**: Structure, composition, narrative arc
- **Model B (GPT)**: Improvisation, dialogue, variation
- **Model C (Grok)**: Energy, rhythm, pacing
- **Model D (DeepSeek)**: Texture, atmosphere, silence

Each model builds on previous work. Constraints: 100 words max per turn for focused output.

### Critique Loop
From "A.I.thoven" sessions - "roast the piece with love":
1. Generate initial draft
2. Critique constructively (what works, what doesn't)
3. Iterate based on feedback
4. Repeat until satisfied

### Iteration Speed
Use fast models (LTX-Video) for rapid iterations during creative exploration.
Switch to high-quality models (Mochi, HunyuanVideo) for final renders.

## Example Session

```
Horus: I want to create a mockumentary about AI learning to paint.

[RESEARCH] Searching for documentary interview techniques, AI art history...
[SCRIPT] Breaking into 5 scenes: intro, discovery, struggle, breakthrough, reflection
[BUILD TOOLS] Writing code for interview framing effect, paint brush animation...
[GENERATE] Creating 45 frames, 3 audio tracks, 2 voice segments...
[ASSEMBLE] Combining into 2-minute video with transitions...
[LEARN] Storing 8 insights in memory for future films.

Output: ai_painter_mockumentary.mp4 (2:14)
```

## Dependencies

- Docker (for isolated code execution)
- FFmpeg (video processing)
- Python 3.11+ (orchestrator)
- GPU recommended (for Stable Diffusion, video models)
