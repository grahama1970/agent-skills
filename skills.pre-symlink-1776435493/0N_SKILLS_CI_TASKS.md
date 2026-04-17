# Task List: Skills CI (Scan + Worktree Fix)

**Created**: 2026-02-04
**Goal**: Add a `skills-ci` skill that scans all skills under `/home/graham/workspace/experiments/pi-mono/.pi/skills`, enforces best‑practice rules, and optionally applies safe fixes in a worktree branch. Default behavior is report‑only. Fix mode must run `sanity.sh` + tests and must not modify the main tree.

## Context

- Custom list of best‑practice skills is supported, but defaults to **all** `best-practices-*` skills.
- Fix mode must run in a **worktree branch** rooted at: `/home/graham/workspace/experiments/pi-mono/.pi/.worktrees/skills-ci`.
- Testing must **assert** correctly and prevent regressions.
- Existing best‑practice rules are in:
  - `best-practices-python` (loguru, typer, httpx, module docstring, <800 LOC)
  - `best-practices-skills` (SKILL.md frontmatter + structure rules)

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| N/A | Standard library / git / bash | N/A | N/A |

> No new third‑party dependencies required. Use stdlib + git CLI only.

## Questions/Blockers

None - all requirements clear.

---

## Tasks

### P0: Setup (Sequential)

- [ ] **Task 1**: Create `skills-ci` skill skeleton
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - Notes: Create `/home/graham/workspace/experiments/pi-mono/.pi/skills/skills-ci/` with `SKILL.md`, `run.sh`, and `sanity.sh`.
  - **Sanity**: None (standard library / well-known packages)
  - **Definition of Done**:
    - Test: Manual check
    - Assertion: `SKILL.md` has valid frontmatter and usage docs; `run.sh` and `sanity.sh` exist and are executable.

- [ ] **Task 2**: Define check registry and configuration
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - Notes: Create `skills_ci.py` with rules for best‑practices‑python + best‑practices‑skills, plus a registry that loads all `best-practices-*` skill folders by default or a custom list via `--best-practices`.
  - **Sanity**: None (standard library / well-known packages)
  - **Definition of Done**:
    - Test: `python skills_ci.py --help`
    - Assertion: CLI shows `--best-practices` and defaults to all `best-practices-*` when not provided.

### P1: Implementation (Parallel)

- [ ] **Task 3**: Implement report‑only scan (default)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - Notes: Scan all skills for violations; emit JSON + Markdown reports. No changes to disk.
  - **Sanity**: `skills-ci/sanity.sh`
  - **Definition of Done**:
    - Test: `skills-ci/sanity.sh`
    - Assertion: Report is produced; main tree is unchanged.

- [ ] **Task 4**: Implement safe worktree branch fix mode
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - Notes: `--apply` should create a worktree under `/home/graham/workspace/experiments/pi-mono/.pi/.worktrees/skills-ci/<branch>`, apply **safe** fixes only (docstrings, loguru/httpx/typer in small files), then run sanity/tests.
  - **Sanity**: `skills-ci/sanity.sh`
  - **Definition of Done**:
    - Test: `skills-ci/sanity.sh --apply`
    - Assertion: Branch created in worktree, sanity + tests pass, main tree clean, and report notes applied changes.

- [ ] **Task 5**: Add minimal tests for the scanner
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - Notes: Add `tests/test_skills_ci.py` (stdlib or pytest) that runs the scan against a tiny fixture and asserts report structure.
  - **Sanity**: None (standard library / well-known packages)
  - **Definition of Done**:
    - Test: `pytest -q skills-ci/tests/test_skills_ci.py`
    - Assertion: Report contains expected keys and counts.

### P2: Validation (After All Previous)

- [ ] **Task 6**: End‑to‑end validation
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3, Task 4, Task 5
  - Notes: Run report‑only scan, then run worktree fix mode, confirm branch created and tests pass.
  - **Sanity**: `skills-ci/sanity.sh`
  - **Definition of Done**:
    - Test: `skills-ci/sanity.sh` + `skills-ci/sanity.sh --apply`
    - Assertion: Report‑only produces no diffs; apply mode produces changes in worktree only and passes tests.

---

## Completion Criteria

- `skills-ci` skill exists with SKILL.md + run/sanity scripts.
- Report‑only scan works and never edits the main tree.
- Worktree branch fix mode works and runs sanity + tests.
- Tests assert report structure and reduce risk of regressions.
- Default best‑practice list is all `best-practices-*`, with custom override support.
