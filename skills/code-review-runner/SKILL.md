---
name: code-review-runner
description: >
  Deterministic code review skill with T0 validators (best-practices-*, ruff, compile)
  and LLM-powered findings (codex/scillm). Scores findings by severity, keeps
  suggested fixes advisory, and fails closed on provider errors. Structured JSON output.
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
  short-description: Deterministic code review with advisory LLM findings
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
disciplines:
  - evaluation-quality
  - developer-tooling
---

# /code-review-runner

Deterministic code review with LLM-powered findings. Two-tier architecture:

- **T0 (deterministic)**: best-practices-* validators, ruff lint, compile() check, file limits
- **T1 (LLM)**: codex/scillm review with structured findings prompt

Each finding is scored by severity. Suggested fixes remain advisory because the runner
does not apply them; current-tree compilation or DoD results cannot validate a proposed
fix. Critical and major findings fail the review until they are reconciled.

SciLLM requests use the active proxy key from the environment or running proxy
container and always send `X-Caller-Skill: code-review-runner`. A 401 from a
stale environment key triggers one retry with the running proxy container key.
The Codex backend uses the current one-shot `gpt-5.5` route and omits
`temperature` and `max_tokens` as required by the SciLLM paved path.
An HTTP failure, empty assistant response, or malformed findings payload makes
the review status `error` and the CLI exits nonzero; zero provider output must
never become PASS.

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
  - Suggested fixes remain advisory until applied and independently checked
  |
  v
Scoring: findings impact is severity-derived; unapplied fixes remain advisory
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
  "max_rounds": 2,
  "base_ref": "origin/main"
}
```

Set `base_ref` for pull-request or branch review. The runner then includes the
authoritative git diff in the model request and fails closed if the diff cannot
be built or is empty. File excerpts are supporting context, not a substitute
for the change set.

## Scoring

| Severity | Weight | Description |
|----------|--------|-------------|
| critical | 1.0 | Security, data loss, crash |
| major | 0.7 | Logic error, contract violation |
| minor | 0.3 | Style, naming, minor inefficiency |
| info | 0.1 | Suggestion, nitpick |

Suggested fixes remain advisory because this runner does not apply them. It
must not mark a fix validated merely because the current tree compiles or its
DoD passes. Critical or major advisory findings remain in the result and fail
the review pending reconciliation. If any requested provider round fails, the
whole review returns `error`; successful rounds cannot mask an unavailable or
unauthorized review round.

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
