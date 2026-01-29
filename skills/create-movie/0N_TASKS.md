# Task List: create-movie Skill for Horus Persona

**Created**: 2026-01-29
**Goal**: Enable Horus to create movies (mockumentaries, short films, music videos, educational content) through an orchestrated workflow that includes writing his own tools.

## Context

Horus needs a skill that allows him to express himself through filmmaking. Unlike simple video generation, this skill enables Horus to:
1. **Research** techniques and tools via /dogpile and /surf
2. **Script** his creative vision with human collaboration
3. **Build Tools** by writing code in a Docker-isolated environment
4. **Generate** visual/audio assets using free/open-source AI tools
5. **Assemble** final output as MP4 video or interactive experiences
6. **Learn** by storing insights in /memory for future recall

Philosophy (from Nobody & The Computer): "AI isn't the artist, it's the amplifier" - Horus uses AI to turn imagination into audiovisual reality.

**Key Insight**: This skill **orchestrates existing skills** rather than reimplementing:
- `/tts-train` - Horus's voice
- `/create-image` - Image generation
- `/dogpile` - Research
- `/memory` - Learnings
- `/surf` - Web research
- Video generation: LTX-Video, Mochi 1 (AI motion video, not just still images)

## Crucial Dependencies (Sanity Scripts)

| Library/Tool | API/Method | Sanity Script | Status |
|--------------|------------|---------------|--------|
| Docker | Container isolation | `sanity/docker.sh` | [x] PASS |
| FFmpeg | Video processing | `sanity/ffmpeg.sh` | [x] PASS |

**Runtime-checked (GPU-optional):**
| Library/Tool | API/Method | Checked At | Notes |
|--------------|------------|------------|-------|
| ComfyUI | Node-based generation | Generate phase | Requires GPU, optional |
| faster-whisper | Speech-to-text | Generate phase | CPU fallback available |
| IndexTTS2 | Text-to-speech | Generate phase | Optional |

> Core sanity scripts PASS. GPU dependencies checked at runtime with graceful fallbacks.

## Questions/Blockers

None - all requirements clarified via user interview:
- Architecture: Orchestrator with phases
- Code environment: Docker-isolated (like /battle, /hack)
- Output formats: Both MP4 and interactive
- Memory: Full integration
- Tools: Free/open-source only

## Tasks

### P0: Setup & Scaffolding (Sequential)

- [x] **Task 1**: Create skill directory structure
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Sanity**: None (filesystem operations)
  - **Definition of Done**:
    - Test: `ls -la .pi/skills/create-movie/`
    - Assertion: Directory contains SKILL.md, run.sh, Dockerfile, orchestrator.py
  - **Completed**: 2026-01-29 - All files created

- [x] **Task 2**: Create Docker environment for code execution
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - **Sanity**: `sanity/docker.sh` (must pass first)
  - **Definition of Done**:
    - Test: `docker build -t horus-movie-sandbox .pi/skills/create-movie/`
    - Assertion: Container builds successfully with Python 3.11, ffmpeg, and base dependencies
  - **Completed**: 2026-01-29 - Dockerfile created with Python 3.11, FFmpeg, imagemagick

- [x] **Task 3**: Create sanity scripts for all dependencies
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - **Definition of Done**:
    - Test: `./sanity/run_all.sh`
    - Assertion: All sanity scripts exit 0
  - **Completed**: 2026-01-29 - docker.sh and ffmpeg.sh pass

### P1: Core Orchestrator (Sequential after P0)

- [ ] **Task 4**: Implement Phase 1 - Research
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1, Task 2, Task 3
  - **Definition of Done**:
    - Test: `python orchestrator.py research "how to create a film noir scene"`
    - Assertion: Returns structured research results from /dogpile, /surf, /memory

- [ ] **Task 5**: Implement Phase 2 - Script
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 4
  - **Definition of Done**:
    - Test: `python orchestrator.py script --research-file research.json`
    - Assertion: Generates scene breakdown with: shots, dialogue, visual descriptions, audio cues

- [ ] **Task 6**: Implement Phase 3 - Build Tools
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2, Task 5
  - **Definition of Done**:
    - Test: `python orchestrator.py build-tools --script-file script.json`
    - Assertion: Generates and executes code in Docker sandbox, outputs tool artifacts

- [ ] **Task 7**: Implement Phase 4 - Generate Assets
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 6
  - **Definition of Done**:
    - Test: `python orchestrator.py generate --tools-dir ./tools --script-file script.json`
    - Assertion: Produces image/video/audio assets in output directory

- [ ] **Task 8**: Implement Phase 5 - Assemble
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 7
  - **Definition of Done**:
    - Test: `python orchestrator.py assemble --assets-dir ./assets --output movie.mp4`
    - Assertion: Produces playable MP4 file or interactive HTML bundle

### P2: Integration & Memory (After P1)

- [ ] **Task 9**: Integrate with /memory skill
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 4, Task 5, Task 6, Task 7, Task 8
  - **Definition of Done**:
    - Test: `python orchestrator.py --store-learnings`
    - Assertion: QRA pairs stored in memory with scope "horus-filmmaking"

- [ ] **Task 10**: Create SKILL.md with triggers and documentation
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: All previous tasks
  - **Definition of Done**:
    - Test: Skill loads in Pi/Claude Code
    - Assertion: Triggers like "create movie", "make film", "horus filmmaking" activate skill

### P3: Validation (After P2)

- [ ] **Task 11**: End-to-end test with sample movie
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: All previous tasks
  - **Definition of Done**:
    - Test: `python orchestrator.py create "A 30-second film about Horus discovering colors"`
    - Assertion: Produces complete movie file, learnings stored in memory

- [ ] **Task 12**: Run skills-broadcast push
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 11
  - **Definition of Done**:
    - Test: `skills-broadcast push`
    - Assertion: Skill synced to all IDE targets

## Technical Architecture

### Orchestrator Phases

```
┌─────────────────────────────────────────────────────────────────┐
│                    create-movie Orchestrator                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐     │
│  │ RESEARCH │ → │  SCRIPT  │ → │  BUILD   │ → │ GENERATE │     │
│  │          │   │          │   │  TOOLS   │   │          │     │
│  │ /dogpile │   │ Human    │   │ Docker   │   │ ComfyUI  │     │
│  │ /surf    │   │ collab   │   │ sandbox  │   │ FFmpeg   │     │
│  │ /memory  │   │ scene    │   │ code     │   │ Whisper  │     │
│  │          │   │ breakdown│   │ writing  │   │ TTS      │     │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘     │
│                                                    │            │
│                                                    ▼            │
│                                            ┌──────────┐         │
│                                            │ ASSEMBLE │         │
│                                            │          │         │
│                                            │ FFmpeg   │         │
│                                            │ concat   │ → MP4   │
│                                            │ HTML     │ → Web   │
│                                            └──────────┘         │
│                                                    │            │
│                                                    ▼            │
│                                            ┌──────────┐         │
│                                            │  LEARN   │         │
│                                            │ /memory  │         │
│                                            └──────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

### Docker Sandbox (for Build Tools phase)

```dockerfile
FROM python:3.11-slim

# Core tools
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python packages for video generation
RUN pip install --no-cache-dir \
    pillow \
    numpy \
    opencv-python-headless \
    moviepy \
    faster-whisper \
    torch --index-url https://download.pytorch.org/whl/cpu

# Security: non-root user, no network by default
RUN useradd -m horus
USER horus
WORKDIR /workspace
```

### Free/Open-Source Tool Stack

| Purpose | Tool | License | Notes |
|---------|------|---------|-------|
| Image Generation | Stable Diffusion (via ComfyUI) | CreativeML Open RAIL-M | Local GPU required |
| Video Generation | LTX-Video, Mochi 1 | Apache 2.0 | Local or API |
| Video Processing | FFmpeg | LGPL/GPL | Industry standard |
| Speech-to-Text | faster-whisper | MIT | CTranslate2 optimized |
| Text-to-Speech | IndexTTS2 | Open source | Free alternative to ElevenLabs |
| Node Workflows | ComfyUI | GPL-3.0 | 100% open source |

## Completion Criteria

- [ ] All sanity scripts pass
- [ ] All tasks marked [x]
- [ ] All Definition of Done tests pass
- [ ] End-to-end movie creation works
- [ ] Learnings stored in /memory
- [ ] skills-broadcast push successful

## Follow-Up: Composable Skills

The following skills should be created/renamed for full composability:

- [ ] **create-story** - Creative writing skill for scripts, narratives, fiction
  - Integrates with /memory for character lore
  - Uses /ingest-book for book inspiration
  - Called by create-movie for Script phase

- [ ] **create-paper** - Rename create-paper for naming consistency
  - Academic/technical papers with citations
  - Formal structure (abstract, methodology, conclusions)

## Notes

### Philosophy: "Vibe Coding" for Horus

Horus doesn't just use pre-built tools - he writes code to create his own tools. The Build Tools phase allows Horus to:
1. Research techniques via /dogpile
2. Write Python/shell scripts to implement techniques
3. Execute in isolated Docker sandbox
4. Iterate on results

This mirrors the "Nobody & The Computer" approach: AI as amplifier, not replacement.

### Memory Integration

After each movie creation, store:
- Successful prompts that worked well
- Tool code that produced good results
- Lessons learned about specific techniques
- Links between concepts (e.g., "film noir" → "high contrast, shadows, venetian blinds")

### Interactive Output Format

For web-based outputs, generate:
```
output/
├── index.html          # Main viewer
├── assets/
│   ├── frames/         # Individual frames
│   ├── audio/          # Audio tracks
│   └── data.json       # Scene metadata
└── player.js           # Interactive controls
```
