# Task List: Align pi-mono skills with best-practices-python

**Created**: 2026-02-04
**Goal**: Align Python-based skills under `/home/graham/workspace/experiments/pi-mono/.pi/skills` with `best-practices-python` rules (loguru, typer, httpx, module docstrings, <800 LOC), without breaking existing workflows.

## Context

- Current scan: 713 Python files, 186 missing module docstrings, 35 use `requests`, 8 use `click`, 92 use `argparse`, 46 use `logging`, 43 files >800 LOC.
- Frontmatter normalization for key skills is already done; remaining mismatch resolved.
- Alignment should be **incremental and safe**: fix small/medium files first, treat large monolith refactors as a separate track.

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| N/A | Standard library / well-known only | N/A | N/A |

> No new third‑party dependencies are required for alignment.

## Questions/Blockers

None - all requirements clear.

---

## Tasks

### P0: Setup (Sequential)

- [ ] **Task 1**: Add a lightweight alignment scanner (stdlib only)
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - Notes: Emit counts + file lists for: missing module docstrings, requests/httpx usage, click/argparse vs typer, logging vs loguru, files >800 LOC.
  - **Sanity**: None (standard library / well-known packages)
  - **Definition of Done**:
    - Test: `sanity/skills_alignment_scan.py`
    - Assertion: Running the scanner prints counts and lists without errors.

- [ ] **Task 2**: Create a small allowlist for large monoliths (no refactor yet)
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - Notes: Create `references/skills_alignment_exceptions.md` with current >800 LOC files and rationale; mark as Phase‑2 refactor candidates.
  - **Sanity**: None (standard library / well-known packages)
  - **Definition of Done**:
    - Test: Manual check
    - Assertion: Exceptions doc lists all >800 LOC files from scan.

### P1: Implementation (Parallel)

- [ ] **Task 3**: Add module docstrings to small/medium Python files
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - Notes: Target files <400 LOC first. Use concise module docstrings (purpose, inputs/outputs, failure modes).
  - **Sanity**: None (standard library / well-known packages)
  - **Definition of Done**:
    - Test: `sanity/skills_alignment_scan.py`
    - Assertion: Missing‑docstring count is reduced to zero for <400 LOC files.

- [ ] **Task 4**: Replace `requests` with `httpx` in small/medium files
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - Notes: Apply to files <400 LOC to minimize risk; keep behavior identical.
  - **Sanity**: None (standard library / well-known packages)
  - **Definition of Done**:
    - Test: `sanity/skills_alignment_scan.py`
    - Assertion: `requests` usage is eliminated for <400 LOC files.

- [ ] **Task 5**: Replace `argparse`/`click` with Typer in small CLIs
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - Notes: Target files <400 LOC. Keep CLI flags stable unless broken. Update run.sh if needed.
  - **Sanity**: None (standard library / well-known packages)
  - **Definition of Done**:
    - Test: `sanity/skills_alignment_scan.py`
    - Assertion: No `argparse`/`click` usage in <400 LOC CLI files.

- [ ] **Task 6**: Replace stdlib `logging` with loguru in small/medium files
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - Notes: Target files <400 LOC. Preserve log messages and severity.
  - **Sanity**: None (standard library / well-known packages)
  - **Definition of Done**:
    - Test: `sanity/skills_alignment_scan.py`
    - Assertion: No `logging` usage in <400 LOC files.

### P2: Validation (After All Previous)

- [ ] **Task 7**: Validate alignment and document remaining exceptions
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 2, Task 3, Task 4, Task 5, Task 6
  - Notes: Run alignment scan and ensure remaining violations are only in the exceptions list.
  - **Sanity**: None (standard library / well-known packages)
  - **Definition of Done**:
    - Test: `sanity/skills_alignment_scan.py`
    - Assertion: All remaining violations are explicitly listed in `references/skills_alignment_exceptions.md`.

---

## Completion Criteria

- Alignment scan exists and runs without errors.
- All <400 LOC Python files in skills have module docstrings and use loguru/httpx/typer.
- Exceptions file documents large monoliths and any remaining violations.
- No behavior regressions in skill CLIs (flags preserved).
