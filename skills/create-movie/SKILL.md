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

### Phase 1: Research
- Use /dogpile to research techniques
- Use /surf to visit tutorials and references
- Recall from /memory what worked before

### Phase 2: Script
- Collaborate with human on creative vision
- Break down into scenes, shots, dialogue
- Define visual style and audio cues

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

# Full orchestrated workflow
./run.sh create "A 30-second film about discovering colors"

# Individual phases
./run.sh research "film noir lighting techniques"
./run.sh script --from-research research.json
./run.sh build-tools --script script.json
./run.sh generate --tools ./tools --script script.json
./run.sh assemble --assets ./assets --output movie.mp4
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
| `/paper-writer` | Write stories, scripts, creative content |
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

## Memory Integration

After each movie, stores:
- Successful prompts
- Working tool code
- Technique insights
- Concept relationships

Scope: `horus-filmmaking`

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
