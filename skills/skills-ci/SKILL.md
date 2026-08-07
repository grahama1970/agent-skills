---
name: skills-ci
description: >
  Scan and optionally fix all skills under .pi/skills using best-practices-* rules,
  with safe worktree branch fixes and sanity/test gating.
triggers:
  - skills ci
  - skill ci
  - skills scan
  - skill scan
  - best practices scan
  - skills audit
allowed-tools:
  - Bash
  - Python
metadata:
  short-description: Skills CI scan + worktree fix
provides:
  - skill-validation
composes:
  - best-practices-skills
  - create-figure
  - memory
  - task-monitor

taxonomy:
  - validation
  - compliance
disciplines:
  - developer-tooling
  - evaluation-quality
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Skills CI

This skill scans all skills under `.pi/skills` and enforces best‑practices rules.
Default mode is **report‑only** (no edits). Optional `--apply` runs safe fixes in
an isolated **worktree branch** and runs `sanity.sh` + tests.

## Usage

```bash
# Report-only scan (default)
./run.sh scan

# Report-only with custom best-practices list
./run.sh scan --best-practices best-practices-python,best-practices-skills

# Report-only with per-skill reports and notification
./run.sh scan --per-skill --per-skill-dir .artifacts/skills --notify pi-mono

# Direct autofix: scan + fix in-place (no worktree, for nightly use)
./run.sh autofix --notify pi-mono --learn

# Apply safe fixes in a worktree branch (with lint, for human review)
./run.sh apply --branch skills-ci-20260204 --lint --lint-scope changed
```

## Guarantees

- Report-only (`scan`) never edits the main tree.
- `autofix` applies safe fixes directly to canonical dir (docstrings, requests→httpx, logging→loguru, missing deps, hatchling removal, frontmatter descriptions). Designed for nightly scheduler use.
- `apply` edits only the worktree branch and runs sanity/tests (for human review).
- Files >400 lines, test fixtures, and excluded paths are never auto-fixed.
- Task monitor is always registered for scan/apply/autofix runs.

## Optional lint integrations

Use `--lint` to run per-skill `lint.sh` scripts when present. This does **not**
auto-run external linters (ruff/black/mypy/eslint) unless your skill provides
its own `lint.sh`, to avoid breaking workflows.

## Per-skill reports and notifications

Use `--per-skill` to emit a report per skill under `--per-skill-dir`. Use
`--notify <project>` to send a summary to `agent-inbox` (for example,
`--notify pi-mono`).

## Task Monitor Integration

Every run registers a task in `task-monitor` and updates a state file under
`.artifacts/skills-ci-<mode>.state.json` (or alongside `--report-json` when set).

## Visualization

After a scan, offer to visualize skill health via `/create-figure`:

```bash
# Skill compliance heatmap (green = healthy, red = violations)
create-figure heatmap --input skills-ci-scan.json --output skill-health.png

# Violation distribution by type
create-figure metrics --input skills-ci-scan.json --output violations.png --type bar --title "Violations by Type"
```

**When to offer:** After presenting scan results with violations, ask: "Want me to generate a skill health heatmap?"

## Common Mistakes

### WRONG: Running autofix without scanning first to establish baseline
```bash
./run.sh autofix  # fixes blindly without knowing baseline error count
```

### RIGHT: Scan first, then fix, then verify error count
```bash
./run.sh scan                # establish baseline violation count
./run.sh autofix --notify pi-mono --learn
./run.sh scan                # verify count is equal or lower
```

### WRONG: Skipping skills-ci after modifying any file under .pi/skills/
```bash
# "I only changed 3 files" is NOT an exception
```

### RIGHT: Always run scan before and after skill changes (NON-NEGOTIABLE)
```bash
cd .pi/skills/skills-ci && uv run python skills_ci.py --mode scan  # before
# ... make changes ...
cd .pi/skills/skills-ci && uv run python skills_ci.py --mode scan  # after
```

### WRONG: Using apply mode without reviewing the worktree branch
```bash
./run.sh apply --branch skills-ci-fix  # applies fixes without human review
```

### RIGHT: Apply creates a branch for human review
```bash
./run.sh apply --branch skills-ci-fix --lint --lint-scope changed
# Review the branch, then merge if satisfied
```
