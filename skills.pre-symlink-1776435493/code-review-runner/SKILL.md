---
name: code-review-runner
description: >
  Deterministic code review skill with T0 validators (best-practices-*, ruff, compile)
  and LLM-powered findings (codex/scillm). Scores finding_severity x fix_validity.
  Self-improvement loop reduces false positives across rounds. Structured JSON output.
  Replaces raw codex exec in orchestrate T2 gate.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
triggers:
  - review code
  - code review runner
  - run code review
  - review changes
  - T2 review gate
  - validate code quality
  - review pull request code
  - check code quality
metadata:
  short-description: Deterministic code review with LLM findings + fix validation
provides:
  - code-review
  - quality-gate
composes:
  - best-practices-python
  - best-practices-d3
  - best-practices-react
  - best-practices-skills
  - review-code
  - memory
taxonomy:
  - review
  - quality
  - orchestration
---

# /code-review-runner

Deterministic code review with LLM-powered findings. Two-tier architecture:

- **T0 (deterministic)**: best-practices-* validators, ruff lint, compile() check, file limits
- **T1 (LLM)**: codex/scillm review with structured findings prompt

Each finding is scored: `severity x fix_validity`. A suggested fix must compile and not
break the DoD to count as valid. The self-improvement loop across rounds reduces false
positives — findings that don't survive validation get downweighted.

## Architecture

```
Input: ReviewSpec (files, cwd, context, dod_command)
  |
  v
T0: Deterministic validators (no LLM)
  - ruff lint (Python files)
  - compile() syntax check (Python files)
  - best-practices-python (800 LOC, loguru, httpx, etc.)
  - best-practices-d3 (D3 anti-patterns for TSX/TS)
  - best-practices-skills (SKILL.md structure)
  |
  v
T1: LLM review (scillm codex or provider of choice)
  - Reads all target files + context
  - Produces structured findings (severity, location, description, fix)
  - Each fix validated: compile() + DoD rerun
  |
  v
Scoring: findings_score = sum(severity * fix_validity) / max_possible
  |
  v
Output: ReviewResult JSON
  - findings[]: severity, location, description, suggested_fix, validated
  - t0_violations[]: deterministic rule violations
  - score: 0.0-1.0 quality score
  - summary: one-line verdict
```

## Usage

```bash
# Review files with default settings (scillm codex)
./run.sh review <spec.json>

# Dry-run: show T0 validators only, no LLM call
./run.sh dry-run <spec.json>

# Parse result
./run.sh result <result.json>
```

## Spec Format

```json
{
  "task_id": "review-auth-module",
  "files": ["src/auth.py", "src/auth_test.py"],
  "cwd": "/path/to/repo",
  "context": "Auth module rewrite for compliance",
  "dod_command": "uv run pytest tests/test_auth.py -q",
  "backend": "codex",
  "max_rounds": 2
}
```

## Scoring

| Severity | Weight | Description |
|----------|--------|-------------|
| critical | 1.0 | Security, data loss, crash |
| major | 0.7 | Logic error, contract violation |
| minor | 0.3 | Style, naming, minor inefficiency |
| info | 0.1 | Suggestion, nitpick |

Fix validity multiplier:
- 1.0 = fix compiles AND DoD still passes
- 0.5 = fix compiles but no DoD to verify
- 0.0 = fix doesn't compile or breaks DoD (false positive)

## Integration

| Skill | Role |
|-------|------|
| `/orchestrate` | T2 gate calls this after code-runner passes |
| `/best-practices-python` | T0 validator: 800 LOC, loguru, httpx, etc. |
| `/best-practices-d3` | T0 validator: D3 anti-patterns |
| `/best-practices-skills` | T0 validator: SKILL.md structure |
| `/review-code` | Fallback for full multi-round review |
| `/memory` | Learn review patterns, recall prior findings |

## Pipeline Position

```
/code-runner (writes code) -> /code-review-runner (reviews it) -> /orchestrate (gates it)
```
