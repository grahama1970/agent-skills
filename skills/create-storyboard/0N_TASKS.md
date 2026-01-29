# Task List: Create-Storyboard Skill

**Created**: 2026-01-29
**Goal**: Implement `create-storyboard` skill to transform screenplay output into simple animatics with camera framing, visual panels, and timing.

## Context

The `create-storyboard` skill transforms `/create-story` screenplay output into pre-production animatics. It sits between SCRIPT and BUILD TOOLS phases in `/create-movie`'s pipeline. The skill provides camera framing auto-selection, multi-fidelity visual panel generation, and FFmpeg-based animatic assembly.

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method          | Sanity Script                | Status      |
| ------- | ------------------- | ---------------------------- | ----------- |
| ffmpeg  | `-i` concat filter  | `sanity/ffmpeg_concat.sh`    | [ ] PENDING |
| pillow  | `Image.composite()` | `sanity/pillow_composite.py` | [ ] PENDING |
| typer   | CLI framework       | N/A (well-known)             | -           |

> All sanity scripts must PASS before proceeding to implementation.

## Questions/Blockers

None - requirements clarified through user interview:

- Output: Simple animatics (video with timing)
- Input: `/create-story` screenplay with embedded notes
- Camera: Taxonomy with auto-selection
- Visuals: Multi-fidelity (sketch/reference/generated)
- Memory: `horus-storyboarding` scope

## Tasks

### P0: Setup (Sequential)

- [x] **Task 1**: Create skill directory structure and SKILL.md
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Sanity**: None (file operations only)
  - **Definition of Done**:
    - Test: `ls .pi/skills/create-storyboard/`
    - Assertion: Contains SKILL.md, run.sh, pyproject.toml
  - **Status**: COMPLETE (files already created)

- [x] **Task 2**: Implement shot_taxonomy.py
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - **Sanity**: None (pure Python)
  - **Definition of Done**:
    - Test: `python shot_taxonomy.py`
    - Assertion: Prints all shot types and auto-selection test results
  - **Status**: COMPLETE (file already created)

- [x] **Task 3**: Create sanity scripts for dependencies
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - **Sanity**: N/A (these ARE the sanity scripts)
  - **Definition of Done**:
    - Test: `./sanity/run_all.sh`
    - Assertion: All scripts exit with code 0

### P1: Core Implementation (Parallel)

- [x] **Task 4**: Implement screenplay_parser.py
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Sanity**: None (pure Python, regex)
  - **Definition of Done**:
    - Test: `python screenplay_parser.py fixtures/sample.md`
    - Assertion: Outputs JSON with scenes, dialogue, action blocks

- [x] **Task 5**: Implement camera_planner.py
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2 (shot_taxonomy.py)
  - **Sanity**: None (uses shot_taxonomy)
  - **Definition of Done**:
    - Test: `python camera_planner.py scenes.json`
    - Assertion: Outputs shot_plan.json with auto-selected shots

- [x] **Task 6**: Implement panel_generator.py
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 3 (sanity scripts pass)
  - **Sanity**: `sanity/pillow_composite.py`
  - **Definition of Done**:
    - Test: `python panel_generator.py shot_plan.json --fidelity sketch`
    - Assertion: Creates panels/ directory with PNG files

### P2: Assembly & Integration (After P1)

- [x] **Task 7**: Implement animatic_assembler.py
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 6
  - **Sanity**: `sanity/ffmpeg_concat.sh`
  - **Definition of Done**:
    - Test: `python animatic_assembler.py panels/ --output test.mp4`
    - Assertion: Creates valid MP4 file with ffprobe metadata

- [x] **Task 8**: Implement orchestrator.py (main CLI)
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Tasks 4, 5, 6, 7
  - **Sanity**: None (integration)
  - **Definition of Done**:
    - Test: `./run.sh create fixtures/sample_screenplay.md`
    - Assertion: Produces output/animatic.mp4

### P3: Memory & Integration (After P2)

- [ ] **Task 9**: Add memory integration (horus-storyboarding scope)
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 8
  - **Sanity**: None (uses /memory skill)
  - **Definition of Done**:
    - Test: `./run.sh create screenplay.md --store-learnings`
    - Assertion: `memory recall "storyboard" --scope horus-storyboarding` returns stored data

- [ ] **Task 10**: Update /create-movie to call /create-storyboard
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 8
  - **Sanity**: None (file edit)
  - **Definition of Done**:
    - Test: Grep for "storyboard" in create-movie/orchestrator.py
    - Assertion: Contains call to create-storyboard skill

### P4: Validation (After All)

- [ ] **Task 11**: Create test fixtures and run full integration test
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: All previous tasks
  - **Definition of Done**:
    - Test: `./sanity.sh`
    - Assertion: All tests pass, sample animatic generated

## Completion Criteria

- [ ] All sanity scripts pass
- [ ] All tasks marked [x]
- [ ] All Definition of Done tests pass
- [ ] `/create-movie` can call `/create-storyboard` as sub-phase
- [ ] Memory integration stores/recalls successfully

## Notes

- Tasks 1-2 are ALREADY COMPLETE (SKILL.md and shot_taxonomy.py created)
- Multi-fidelity panel generation:
  - `sketch`: ASCII/Mermaid diagrams (fast, rough)
  - `reference`: Fetch via /surf, /ingest-movie (medium, varied)
  - `generated`: AI via /create-image FLUX.1 (slow, high quality)
- Reference repos to clone for study:
  - `git clone https://github.com/HKUDS/ViMax.git`
  - `git clone https://github.com/wonderunit/storyboarder.git`
  - `git clone https://github.com/afterwriting/aw-parser.git`
