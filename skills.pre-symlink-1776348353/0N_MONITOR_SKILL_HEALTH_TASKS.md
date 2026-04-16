# Task List: monitor-skill-health

**Created**: 2026-02-17
**Goal**: Build a nightly monitor that audits registered skills against best-practices packs, stores actionable findings in memory, and emits aggregate trend-friendly summaries.

## Context

Create `.pi/skills/monitor-skill-health` as a composition-first skill. It should reuse existing skills (`assess`, `review-code`, `memory`, `scheduler`, `task-monitor`) and keep custom code limited to orchestration and report normalization.

## Crucial Dependencies (Sanity Scripts)

| Library/Skill | API/Method | Sanity Script | Status |
|---|---|---|---|
| `assess` | `assess.py run <path> --output` | `monitor-skill-health/sanity.sh` | [x] VERIFIED |
| `memory` | `run.sh learn --problem --solution --tag` | `monitor-skill-health/sanity.sh` | [x] VERIFIED |
| `scheduler` | `run.sh register --name --command --cron` | `monitor-skill-health/sanity.sh` | [x] VERIFIED |

## Questions/Blockers

None.

## Tasks

### P0: Scaffolding (Sequential)

- [x] **Task 1**: Create skill skeleton (`SKILL.md`, `run.sh`, `pyproject.toml`, `sanity.sh`, `monitor.py`)
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Definition of Done**:
    - Test: `.pi/skills/monitor-skill-health/run.sh --help`
    - Assertion: CLI shows `audit`, `status`, `history`, `register` commands.

### P1: Core Audit Pipeline (Sequential)

- [x] **Task 2**: Implement skill discovery + composed assess pipeline
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Definition of Done**:
    - Test: `.pi/skills/monitor-skill-health/run.sh audit --limit 2 --json`
    - Assertion: Produces per-skill JSON findings including `works_well`, `needs_fix`, `aspirational_gaps`, `next_steps`.

- [x] **Task 3**: Implement aggregate summarized report + trend history
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - **Definition of Done**:
    - Test: `.pi/skills/monitor-skill-health/run.sh audit --limit 2`
    - Assertion: Writes `latest_summary.json` and `history.jsonl` with severity totals and top issues.

### P2: Integrations (Sequential)

- [x] **Task 4**: Add memory learn integration for run summary and critical findings
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3
  - **Definition of Done**:
    - Test: `.pi/skills/monitor-skill-health/run.sh audit --limit 1 --no-memory --json`
    - Assertion: Memory integration can be toggled off cleanly; default path builds valid memory payloads.

- [x] **Task 5**: Add scheduler register + status/history commands and task-monitor state file
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 4
  - **Definition of Done**:
    - Test: `.pi/skills/monitor-skill-health/run.sh register --help`
    - Assertion: Register command prints intended scheduler job and supports nightly cadence.

### P3: Validation

- [x] **Task 6**: Run sanity + repo checks
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 5
  - **Definition of Done**:
    - Test: `.pi/skills/monitor-skill-health/sanity.sh` and `npm run check`
    - Assertion: Sanity passes; repository checks pass with no new errors introduced.

## Completion Criteria

- [x] Skill can run nightly audits over registered skills.
- [x] Per-skill findings are actionable for a follow-up project agent.
- [x] Aggregate summary report is generated every run.
- [x] Outputs are traceable over time via history + task state.
- [x] Memory payload generation exists and is robust.

## Notes

- Prefer composition over bespoke analysis logic.
- Limit bespoke checks to lightweight normalization and severity mapping.
