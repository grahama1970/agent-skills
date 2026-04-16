# Code Review Request: Battle Skill Modularization

## Repository and branch

- **Repo:** `pi-mono`
- **Branch:** `main`
- **Paths of interest:**
  - `.pi/skills/battle/config.py`
  - `.pi/skills/battle/state.py`
  - `.pi/skills/battle/memory.py`
  - `.pi/skills/battle/scoring.py`
  - `.pi/skills/battle/digital_twin.py`
  - `.pi/skills/battle/red_team.py`
  - `.pi/skills/battle/blue_team.py`
  - `.pi/skills/battle/orchestrator.py`
  - `.pi/skills/battle/report.py`
  - `.pi/skills/battle/qemu_support.py`
  - `.pi/skills/battle/battle.py`

## Summary

Modularized the battle skill from a 3720-line monolith into 11 separate debuggable modules. All modules are under 500 lines. This review focuses on code quality, not security (security review was done previously).

## Objectives

### 1. Check for circular imports

Verify import structure is clean and no circular dependencies exist.

### 2. Review API consistency

Ensure consistent naming, parameter ordering, and return types across modules.

### 3. Verify thread safety

Check that concurrent Red/Blue team execution is properly thread-safe.

### 4. Review error handling

Ensure all exceptions are properly caught and handled.

### 5. Check type hints

Verify type hints are complete and accurate.

### 6. Review documentation

Ensure docstrings are present and accurate.

## Module Line Counts

- config.py: 58 lines
- state.py: 308 lines
- memory.py: 310 lines
- scoring.py: 133 lines
- digital_twin.py: 252 lines
- red_team.py: 226 lines
- blue_team.py: 245 lines
- orchestrator.py: 240 lines
- report.py: 101 lines
- qemu_support.py: 341 lines
- battle.py: 214 lines

## Constraints for the patch

- **Output format:** Unified diff only, inline inside a single fenced code block.
- Include a one-line commit subject on the first line of the patch.
- Patch must apply cleanly.
- No destructive defaults; retain existing behavior.

## Acceptance criteria

- No circular imports
- Type hints complete
- Thread safety verified
- Error handling complete
- Documentation present

## Test plan

**After change:**

1. Run `./sanity.sh` - must pass
2. Run `./run.sh --help` - must show help
3. Run `./run.sh status` - must work

## Deliverable

- Reply with a single fenced code block containing a unified diff
