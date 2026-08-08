---
name: code-runner
triggers:
  - run code and debug
  - self-improvement loop for code
  - run until DoD passes
  - code runner
  - deterministic code execution
  - run and fix code
description: Minimal deterministic code runner for bounded implementation tasks. Runs one LLM backend through /scillm inside a disposable git worktree, enforces a write allowlist, runs a deterministic definition of done, and returns an allowlist-scoped patch artifact for project-agent review.
provides:
  - code-execution
  - bounded-code-fix
composes:
  - scillm
  - project-knowledge
  - agentic-evals
taxonomy:
  - execution
  - quality
disciplines:
  - agentic-orchestration
  - developer-tooling
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Code Runner

> REBUILT 2026-05-06. The legacy monolithic runner is archived at
> `.archive/legacy-2026-05-06/code_runner.py`. The replacement runtime lives in
> `src/code_runner/` and is gated by the historical live E2E suite documented in
> `REWRITE_REQUIREMENTS.md`.

`/code-runner` is intentionally minimal. It is a bounded worker, not an
orchestrator, planner, reviewer, memory system, symbol indexer, or backend race
harness. `/project-knowledge` is composed as an outer tracking surface for
stability decisions and feature reintegration status; it is not exposed as a
tool inside the code-runner loop.

Core flow:

```
task-spec.json
  → deterministic preflight
  → disposable git worktree
  → /scillm SSE tool-use loop
  → deterministic DoD command
  → keep best allowlist-scoped patch
  → result artifacts for project-agent review
```

## Non-Goals Disabled for v1

These are explicitly out of the core runner until the minimal path is reliable:

- `/memory` recall or logging inside the runner loop
- `/project-knowledge` writes inside the runner loop
- `/treesitter` symbol extraction
- `/thunderdome` backend racing
- `/orchestrate` plan dispatch
- `/prompt-lab` template assembly
- `/review-code` auto-review
- backend fallback chains
- predecessor patch chaining
- live-service ownership

Future versions may add these as outer layers. They must not be required for the basic runner to pass.

## Project Knowledge Tracking

Use `PROJECT_KNOWLEDGE.md` in this skill directory to track:

- stability evidence for the narrow patch-only path,
- brittle features currently disabled,
- explicit criteria for re-integrating each feature,
- dated decisions that should be synced through `/project-knowledge` when memory is healthy.

The project agent or `/orchestrate` may update project knowledge before or after
a run. The code-runner process itself must not write project knowledge during
execution; doing so would mix patch execution with coordination state and make
the minimal runner harder to trust.

## Task Contract

Required fields:

| Field | Required | Description |
|-------|----------|-------------|
| `task_id` | Yes | Unique local artifact identifier |
| `title` | Yes | Human-readable task title |
| `prompt` | Yes | Concrete implementation instruction |
| `backend` | Yes | One backend for this run, usually `codex` |
| `cwd` | Yes | Source git repository |
| `output_dir` | Yes | Artifact directory |
| `allowlist` | Yes | Only these paths may be written |
| `definition_of_done.command` | Yes | Deterministic verification command |
| `definition_of_done.assertion` | Yes | Expected output substring or `exit_code == N` |
| `max_rounds` | No | Default: `5` |
| `read_context` | No | Extra read-only files included in prompt context |
| `dirty_worktree_policy` | No | Only `isolated_worktree` is supported |
| `apply_to_source` | No | Explicit opt-in complete-task mode; default `false` |
| `commit_on_success` | No | If `apply_to_source` is true, commit allowlisted source changes after source DoD passes |
| `rollback_on_failure` | No | If source apply or source DoD fails, restore allowlisted source paths; default `true` |

Example:

```json
{
  "task_id": "fix-auth",
  "title": "Fix authentication bug",
  "prompt": "Fix the TypeError in src/auth.py without changing public API behavior.",
  "backend": "codex",
  "cwd": "/path/to/project",
  "output_dir": "/tmp/code-runner-output",
  "allowlist": ["src/auth.py", "tests/test_auth.py"],
  "definition_of_done": {
    "command": "python -m pytest tests/test_auth.py -q",
    "assertion": "passed"
  },
  "dirty_worktree_policy": "isolated_worktree",
  "max_rounds": 5,
  "apply_to_source": false
}
```

## Usage

```bash
./run.sh dry-run task-spec.json --explain-risk
./run.sh run task-spec.json
./run.sh status /tmp/code-runner-output --tail-events 25
./run.sh watch /tmp/code-runner-output
./run.sh doctor --json
```

By default, the project agent must inspect `result.json`, `response.txt`, and the patch artifact before applying changes to the source repo.

Complete-task mode is explicit opt-in:

```json
{
  "apply_to_source": true,
  "commit_on_success": true,
  "rollback_on_failure": true
}
```

In complete-task mode, `/code-runner` still proves the change in a disposable
worktree first. Only after the isolated DoD passes does it apply the allowlist
patch to the source repo, run the same DoD in source, commit only allowlisted
paths, and report `source_commit`. If source apply or source DoD fails, it
restores allowlisted source paths when `rollback_on_failure` is true.

## Safety Model

- Creates a disposable git worktree from the source repo.
- Sets `CODE_RUNNER_SOURCE_CWD` so tool commands that reference the source repo are blocked.
- Enforces the write allowlist in file tools and patch export.
- Blocks destructive shell command patterns.
- Fails if the source repo status changes during a run.
- Removes the disposable worktree after the run.
- Default mode never commits or stages source-repo files.
- Complete-task mode is opt-in and fails before apply if dirty source paths overlap the allowlist.
- Complete-task commits stage only allowlisted paths and fail if unrelated staged paths would be included.

## Tool Surface

The LLM may call only these tools:

| Tool | Purpose |
|------|---------|
| `read_file` | Read bounded file content |
| `edit_file` | Replace a line range after reading |
| `write_file` | Create or rewrite an allowlisted file |
| `run_command` | Run bounded verification commands in the worktree |
| `search_code` | Ripgrep search inside the worktree |

No dynamic skills are exposed as tools.

## Scoring

DoD is dominant:

- Passing DoD can score up to `1.0`.
- Failing DoD is capped below `0.5`.
- Improved rounds are kept in the disposable worktree.
- Regressed rounds are discarded back to the best patch state.

## Output

```
{output_dir}/
  {task_id}.request.json
  {task_id}.status.json
  {task_id}.events.jsonl
  {task_id}.rounds.jsonl
  {task_id}.response.txt
  {task_id}.result.json
  {task_id}.hunk.md
  {task_id}.verifier.log
```

When complete-task mode is enabled, `{task_id}.result.json` also includes:

- `apply_to_source`
- `source_patch_applied`
- `source_dod_passed`
- `source_commit`
- `source_rollback_applied`
- `source_apply_error`

## Valid Task Shape

Good tasks are small and executable:

```text
Implement the documented behavior in src/parser.py.
Only edit src/parser.py and tests/test_parser.py.
Run python -m pytest tests/test_parser.py -q and require "passed".
```

Bad tasks are architectural, vague, or unverifiable:

```text
Improve the architecture.
Make the UI better.
Fix whatever is wrong.
Pass by checking that a string exists in a file.
```

## Acceptance Standard

Patch-only mode is considered reliable only after repeated real runs show:

- source `HEAD` unchanged,
- source working tree unchanged except pre-existing user changes,
- disposable worktree removed,
- patch artifact scoped to `allowlist`,
- DoD result recorded in `result.json`,
- project agent can apply/reject the patch explicitly.

Complete-task mode is considered reliable only after repeated real runs show:

- isolated worktree DoD passes before source mutation,
- source dirty paths overlapping `allowlist` fail closed before apply,
- source patch applies only after isolated success,
- source DoD passes after apply,
- source commit is created when `commit_on_success` is true,
- failed source apply or source DoD restores allowlisted paths,
- source working tree is clean after source DoD, blind checks, and review byproduct cleanup,
- `result.json` records `source_commit`, `source_dod_passed`, and rollback state.

After material stability changes or feature reintegration tests, update
`PROJECT_KNOWLEDGE.md` and sync it through `/project-knowledge` when `/memory` is
available.
