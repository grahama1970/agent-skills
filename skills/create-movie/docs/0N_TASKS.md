# Task List: create-movie Skill for Horus Persona

**Created**: 2026-01-29
**Updated**: 2026-02-04
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
- `/create-score` - Scene music generation (NEW)
- `/dogpile` - Research
- `/memory` - Learnings
- `/surf` - Web research
- Video generation: Google Veo (via HorusShotSpec YAML)

## Crucial Dependencies (Sanity Scripts)

| Library/Tool | API/Method | Sanity Script | Status |
|--------------|------------|---------------|--------|
| Docker | Container isolation | `sanity/docker.sh` | [x] PASS |
| FFmpeg | Video processing | `sanity/ffmpeg.sh` | [x] PASS |

**Runtime-checked (GPU-optional):**
| Library/Tool | API/Method | Checked At | Notes |
|--------------|------------|------------|-------|
| Veo API | Video generation | Generate phase | Requires GEMINI_API_KEY |
| create-score | Music generation | Generate phase | Optional, graceful fallback |
| tts-train | Text-to-speech | Generate phase | Optional |

> Core sanity scripts PASS. GPU dependencies checked at runtime with graceful fallbacks.

## Questions/Blockers

None - all requirements clarified via user interview:
- Architecture: Orchestrator with phases
- Code environment: Docker-isolated (like /battle, /hack)
- Output formats: Both MP4 and interactive
- Memory: Full integration
- Tools: Free/open-source only

## Tasks

### P0: Setup & Scaffolding (Sequential) - COMPLETE

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

### P1: Core Orchestrator (Sequential after P0) - COMPLETE

- [x] **Task 4**: Implement Phase 1 - Research
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1, Task 2, Task 3
  - **Definition of Done**:
    - Test: `./run.sh research "how to create a film noir scene"`
    - Assertion: Returns structured research results from /dogpile, /memory
  - **Completed**: 2026-01-30 - Library-first research with /memory, /dogpile, /ingest-movie, /ingest-youtube

- [x] **Task 5**: Implement Phase 2 - Script
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 4
  - **Definition of Done**:
    - Test: `./run.sh script --from-research research.json --use-create-story`
    - Assertion: Generates scene breakdown with: shots, dialogue, visual descriptions, audio cues
  - **Completed**: 2026-01-30 - Integrates with /create-story, parses INT./EXT. format

- [x] **Task 6**: Implement Phase 3 - Build Tools
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2, Task 5
  - **Definition of Done**:
    - Test: `./run.sh build-tools --script script.json`
    - Assertion: Generates and executes code in Docker sandbox, outputs tool artifacts
  - **Completed**: 2026-01-30 - Docker sandbox execution with tool analysis

- [x] **Task 7**: Implement Phase 4 - Generate Assets
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 6
  - **Definition of Done**:
    - Test: `./run.sh generate --script script.json --tools ./tools`
    - Assertion: Produces image/video/audio assets in output directory
  - **Completed**: 2026-02-04 - Integrated /create-image, /tts-train, /create-score

- [x] **Task 8**: Implement Phase 5 - Assemble
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 7
  - **Definition of Done**:
    - Test: `./run.sh assemble --assets ./assets --output movie.mp4`
    - Assertion: Produces playable MP4 file or interactive HTML bundle
  - **Completed**: 2026-01-30 - FFmpeg concat, HTML export with frame viewer

### P2: Integration & Memory (After P1) - COMPLETE

- [x] **Task 9**: Integrate with /memory skill
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 4, Task 5, Task 6, Task 7, Task 8
  - **Definition of Done**:
    - Test: `./run.sh learn --project-dir ./movie_project`
    - Assertion: QRA pairs stored in memory with scope "horus-filmmaking"
  - **Completed**: 2026-01-31 - learn command extracts and stores insights

- [x] **Task 10**: Create SKILL.md with triggers and documentation
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: All previous tasks
  - **Definition of Done**:
    - Test: Skill loads in Pi/Claude Code
    - Assertion: Triggers like "create movie", "make film", "horus filmmaking" activate skill
  - **Completed**: 2026-01-31 - Comprehensive SKILL.md with all phases documented

### P3: Validation (After P2) - IN PROGRESS

- [x] **Task 11**: End-to-end test with sample movie
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: All previous tasks
  - **Definition of Done**:
    - Test: `./run.sh create "A 30-second film about Horus discovering colors"`
    - Assertion: Produces complete movie file, learnings stored in memory
  - **Completed**: 2026-02-01 - Full workflow tested with Veo rendering

- [ ] **Task 12**: Run skills-broadcast push
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 11
  - **Definition of Done**:
    - Test: `skills-broadcast push`
    - Assertion: Skill synced to all IDE targets
  - **Note**: Pending skill stabilization

### P4: Agent Usability (NEW - 2026-02-04)

- [x] **Task 13**: Create AGENTS.md operator guide
  - Agent: general-purpose
  - Dependencies: Task 10
  - **Definition of Done**:
    - Test: AGENTS.md exists with quick start, examples, error recovery
    - Assertion: Agents can use skill with minimal guidance
  - **Completed**: 2026-02-04 - Comprehensive agent guide

- [x] **Task 14**: Integrate /create-score for music generation
  - Agent: general-purpose
  - Dependencies: Task 7
  - **Definition of Done**:
    - Test: Generate phase calls create-score for audio cues
    - Assertion: Scene music generated with HMT bridge attributes
  - **Completed**: 2026-02-04 - Full integration with bridge extraction

- [ ] **Task 15**: Remove hardcoded paths
  - Agent: general-purpose
  - Dependencies: none
  - **Definition of Done**:
    - Test: grep for /home/graham returns no matches in Python files
    - Assertion: All paths are relative or use environment variables
  - **Note**: music_client.py still has hardcoded paths

- [ ] **Task 16**: Simplify CLI deprecated options
  - Agent: general-purpose
  - Dependencies: none
  - **Definition of Done**:
    - Test: --help shows clean options without deprecated flags
    - Assertion: Deprecated options removed or hidden

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
│  │ /dogpile │   │ /create- │   │ Docker   │   │ /create- │     │
│  │ /memory  │   │  story   │   │ sandbox  │   │  image   │     │
│  │ /ingest- │   │ scene    │   │ code     │   │ /create- │     │
│  │  movie   │   │ breakdown│   │ writing  │   │  score   │     │
│  └──────────┘   └──────────┘   └──────────┘   │ /tts     │     │
│                                               └──────────┘     │
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

### Skill Integration Map

| Skill | Phase | Purpose |
|-------|-------|---------|
| `/ops-workstation` | 0 | Hardware detection |
| `/memory` | 1, 6 | Recall/store knowledge |
| `/dogpile` | 1 | Deep research |
| `/ingest-movie` | 1 | Find reference films |
| `/ingest-youtube` | 1 | Find tutorials |
| `/create-story` | 2 | Screenplay generation |
| `/create-image` | 4 | Image generation |
| `/create-score` | 4 | Scene music (NEW) |
| `/tts-train` | 4 | Voice narration |

### Free/Open-Source Tool Stack

| Purpose | Tool | License | Notes |
|---------|------|---------|-------|
| Image Generation | /create-image (FAL SDK) | Various | Cloud API |
| Video Generation | Google Veo | Google ToS | Via GEMINI_API_KEY |
| Video Processing | FFmpeg | LGPL/GPL | Industry standard |
| Music Generation | /create-score (ACE-Step) | Apache 2.0 | Docker service |
| Text-to-Speech | /tts-train | Various | Horus voice |

## Completion Criteria

- [x] All sanity scripts pass
- [x] All P0-P2 tasks marked [x]
- [x] AGENTS.md created for agent usability
- [x] /create-score integrated for music
- [ ] Hardcoded paths removed
- [ ] skills-broadcast push successful

## Follow-Up: Composable Skills

- [x] **create-story** - Creative writing skill for scripts, narratives, fiction
  - Integrates with /memory for character lore
  - Uses /ingest-book for book inspiration
  - Called by create-movie for Script phase

- [x] **create-score** - Scene music generation
  - Uses ACE-Step via Docker
  - HMT bridge integration
  - Called by create-movie for Generate phase

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
