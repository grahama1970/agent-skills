---
name: code-runner
triggers:
  - run code and debug
  - self-improvement loop for code
  - run until DoD passes
  - code runner
  - deterministic code execution
  - run and fix code
  - autoresearch for code
description: Deterministic self-improvement loop for code tasks. LLM proposes code → apply to disk → T0 deterministic scoring (errors, lint, DoD) → git commit/revert (autoresearch pattern) → /scillm structured fix with full trajectory + /memory recall + /treesitter symbols → strategy escalation. Loops until DoD passes or max rounds exhausted. Project agent reviews final output.
provides:
  - code-execution
  - self-improvement
composes:
  - scillm
  - memory
  - treesitter
  - thunderdome
  - review-code
  - orchestrate
  - prompt-lab
taxonomy:
  - execution
  - quality
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Code Runner

Deterministic self-improvement loop for code authoring tasks. Same pattern as
`/classifier-lab` (backbone training) and Karpathy's autoresearch (LLM training)
but for code quality.

```
LLM proposes → apply to disk → T0 score → improved? git commit : git revert
  → /scillm fix with trajectory + /memory + /treesitter → repeat
```

## Why This Exists

Subagents (claude -p, codex) have ~35% success rate on code tasks. They propose
code but don't verify it runs. Code-runner adds the verification loop + the
autoresearch keep/discard pattern + cross-session memory.

Three-layer quality gate:
1. **T0 (deterministic)**: Does the code run? Does DoD pass? Lint clean? Best-practices?
2. **T1.5 (/scillm)**: Given the evidence + trajectory + past fixes, propose a structured fix
3. **T2 (project agent)**: Is the approach correct? Accept or reject the final output

## The Self-Improvement Loop

```
Round 1: /scillm proposes code (system prompt = v2 template from /prompt-lab)
  → parse v2 hybrid format: JSON metadata + diff + complete file per ### FILE: block
  → try diff first (cheap), fall back to complete file (safe)
  → atomic write to disk (temp → validate → rename)
  → T0 evidence: run DoD, classify errors (regex), ruff lint, best-practices
  → composite score (0.0-1.0, DoD-dominant)
  → score > best + ε? → git commit written files (KEEP) : git checkout (DISCARD)
  → log to llm_invocations collection (ALL rounds — failures are training signal)
  → DoD passed? → DONE, send to project agent for review

Round 2+: Memory-backed system prompt (refreshed each round):
  → original request as IMMUTABLE anchor (prevents drift)
  → DoD + allowlist + last 2 rounds (local history)
  → /memory recall similar solved problems (cross-session)
  → /memory recall by error type (what worked for this error before)
  → /treesitter symbols from modified files
  → strategy escalation instruction (structured_analysis, different_approach, simplify)
  → proposes fix → apply → score → keep/discard → repeat
```

## Usage

```bash
# Run a task spec
./run.sh run task-spec.json

# Custom max rounds
./run.sh run task-spec.json --max-rounds 5

# Specific backend
./run.sh run task-spec.json --backend codex

# Dry run — show what would execute
./run.sh dry-run task-spec.json

# Review changes with hunk (or git diff fallback)
./run.sh review                        # latest working tree diff
./run.sh review output/task-id.hunk.md  # specific review file
```

## Task Spec Format

```json
{
  "task_id": "fix-auth",
  "title": "Fix authentication bug in login handler",
  "prompt": "Read src/auth.py and fix the TypeError on line 45...",
  "backend": "codex",
  "cwd": "/home/graham/workspace/project",
  "output_dir": "/tmp/code-runner-output",
  "allowlist": ["src/auth.py", "tests/test_auth.py"],
  "definition_of_done": {
    "command": "cd /home/graham/workspace/project && python -m pytest tests/test_auth.py -q",
    "assertion": "passed"
  },
  "max_rounds": 5
}
```

### Spec Fields

| Field | Required | Description |
|-------|----------|-------------|
| `task_id` | Yes | Unique identifier (used in /memory, git commits, logs) |
| `title` | Yes | Human-readable task description |
| `prompt` | Yes | Full task instruction for the LLM |
| `backend` | Yes | LLM backend: `codex`, `text`, `gemini`, `claude`, `deepseek`; Codex-era model aliases like `gpt-5.5` normalize to canonical backends |
| `cwd` | Yes | Working directory (must be a git repo for keep/discard) |
| `output_dir` | Yes | Where to write logs, rounds, result.json |
| `allowlist` | No | Files or directories the LLM can write. Supports dir scopes: `"scripts/"` allows any file under scripts/. Default: any file under cwd |
| `definition_of_done.command` | Yes | Shell command to verify correctness |
| `definition_of_done.assertion` | No | Substring that must appear in output, or `exit_code == N` |
| `max_rounds` | No | Max self-improvement rounds (default: 5) |
| `read_context` | No | Files for interface-map context (read-only, not editable) |
| `blind_tests` | No | Hidden tests for /orchestrate blind eval (code-runner never sees these) |
| `timeout_seconds` | No | Per-task timeout in seconds (default: 1800) |

**Round timeout:** Each LLM round has a per-round timeout from `common/estimate_timeout.py`. Uses `max(historical_P95, 180s)` with 1.2x buffer — minimum 216s per round. Override with `CODE_RUNNER_ROUND_TIMEOUT` env var (seconds).
| `escalation_chain` | No | Backend escalation: `[["codex","medium"],["codex","high"],["claude","high"]]` |

## Output

```
{output_dir}/
  {task_id}.response.txt      — final LLM response (for project agent review)
  {task_id}.round_1.txt       — round 1 LLM response
  {task_id}.round_2.txt       — round 2 LLM response (if needed)
  {task_id}.rounds.jsonl      — experiment log (all rounds, local)
  {task_id}.result.json       — final result summary
  {task_id}.hunk.md           — hunk-compatible diff review with trajectory annotations
```

### Hunk Review

After each run, code-runner generates a `{task_id}.hunk.md` with the git diff
and a trajectory table (rounds, scores, strategies). View it with:

```bash
hunk patch output/task-id.hunk.md   # TUI diff viewer with annotations
# or
./run.sh review output/task-id.hunk.md
```

Requires `hunkdiff` (`npm i -g hunkdiff`). Falls back to `cat` if not installed.

### result.json

```json
{
  "task_id": "fix-auth",
  "title": "Fix authentication bug",
  "status": "pass",
  "rounds": 2,
  "best_score": 1.0,
  "dod_passed": true,
  "backend": "codex",
  "best_commit": "a1b2c3d4",
  "round_details": [
    {"round": 1, "score": 0.45, "strategy": "direct_fix", "status": "keep", "error_severity": "contract"},
    {"round": 2, "score": 1.00, "strategy": "structured_analysis", "status": "keep", "dod_passed": true}
  ]
}
```

## Scoring

Composite score (0.0 = broken, 1.0 = perfect). **DoD is dominant.**

| DoD Result | Base | Formula |
|------------|------|---------|
| **PASSED** | 0.50 | + 0.25×(1 - errors/10) + 0.15×(1 - lint/20) + 0.10×(no BP violations) |
| **FAILED** | 0.00 | 0.30×(1 - errors/10) + 0.15×(1 - lint/20) + 0.05×(no BP) — **capped at 0.49** |

Keep/discard uses epsilon threshold (0.01) to avoid churn.

## Strategy Escalation

| Round | Strategy | Instruction |
|-------|----------|-------------|
| 1 | `direct_fix` | Send error, ask for specific fix |
| 2 | `structured_analysis` | Classify error type, analyze systematically |
| 3 | `different_approach` | Previous approach failed — try fundamentally different |
| 4 | `simplify` | Minimum viable, remove all complexity |
| 5 | `escalate` | Write full diagnosis for project agent |

**Escalation accelerates on repeat errors:** if the same error severity appears
in consecutive rounds, strategy jumps ahead (e.g., round 2 with repeat import
error → skip to `different_approach`).

## Source Grounding Verification

On round 2+, code-runner verifies that the LLM's fix actually references the
error it's supposed to fix. This catches hallucinated fixes that don't address
the actual problem.

**Grounding terms extracted from stderr:**
- File names (e.g., `cache.py`)
- Error type keywords (e.g., `TypeError`, `ImportError`)
- Quoted identifiers from error messages
- Line numbers

**Grounding score:** 0.0–1.0 based on how many terms the response references.
If score < 0.5, a reminder is appended to the next round's prompt:

```
IMPORTANT: Your fix must address the ACTUAL error shown above.
The error is in cache.py at line 42.
Reference these specific terms: TypeError, get_value
The actual error message is: TypeError: 'NoneType' object is not subscriptable
```

Emits `grounding_low` event when triggered. Grounding score is tracked in
`llm_metadata` and round details.

### Escalation Chain (backend + reasoning)

When the same error severity repeats, code-runner also escalates the LLM:

```
Step 0: backend:medium   (default — e.g., codex at medium reasoning)
Step 1: backend:high     (same backend, more reasoning effort + 2x max_tokens)
Step 2: claude:high      (switch to Claude Opus as last resort)
```

- **Dynamic temperature:** increments by 0.1 on each repeated error (breaks local minima)
- **Pre-write lint gate:** Python files are `compile()`-checked before writing to disk

Override via spec:
```json
"escalation_chain": [["codex", "medium"], ["codex", "high"], ["claude", "high"]]
```

## Git Integration (Autoresearch Pattern)

- **Before run:** fail closed if tracked worktree changes already exist; use an isolated worktree for dirty projects
- **After each round:** score improved? → `git add -- <written_files>` + `git commit` (KEEP)
- **Score didn't improve:** `git checkout <best_commit> -- <written_files>` (DISCARD)

Only written files are staged/reverted. Never `git add -A`. Never `git reset --hard`.
User work is never hidden with `git stash`. Set `CODE_RUNNER_DIRTY_POLICY=allow`
only when the caller intentionally accepts dirty-worktree risk.

## llm_invocations (Unified Agent Turn Logging)

**ALL rounds** are stored to ArangoDB `llm_invocations` collection via `common/llm_invocations.log_invocation()`:

```python
log_invocation(
    agent="code-runner",
    session_key="cr-fix-auth-1774789000",
    round=2,
    outcome="success",  # or "failed"
    score=1.0,
    model="gpt-5.5",
    tags=["code-runner", "task:fix-auth", "strategy:structured_analysis", "outcome:pass"],
    metadata={"task_id": "fix-auth", "errors_by_type": {}, "commit": "abc123", ...},
)
```

Write-only via memory daemon `/store` endpoint. No bespoke AQL — querying uses `/memory recall`.

**Requires:** `SKILLS_DIR` env var (set by `run.sh`) or `common/` as sibling of skill directory. The module is imported at startup via `sys.path` from `$SKILLS_DIR/common/llm_invocations.py`.

**session_key** links all rounds for one invocation. Enables:
- `/recommend-skill-chain` traversal across related sessions
- `/memory recall` finding what worked for similar error types
- `/episodic-archiver` linking code-runner sessions to conversations

**Recall** on each round queries `/memory` twice:
1. By task description — "have I solved this problem before?"
2. By error type — "have I seen this error severity before?"

Both filter for `outcome:pass` at recall time. Failed rounds ARE stored
(with `outcome:fail` tag) but filtered out during recall.

## /treesitter Integration (Deterministic Code Context)

Before building each fix prompt, `/treesitter` extracts symbols from modified files:

```
src/auth.py:
  function: login(user: str, password: str) → bool
  function: validate(token: str) → dict
  class: AuthHandler
  import: httpx, json, from loguru import logger
```

This gives the /scillm fix call deterministic context — no hallucinated function
signatures. Stored in llm_invocations metadata so recalled fixes include the code structure.

## File Safety

- **Denylist:** `.git`, `.gitignore`, `.env`, `SKILL.md`, `run.sh`, `sanity.sh`, `pyproject.toml`, `package.json`
- **Allowlist:** If `allowlist` is in task spec, ONLY those files can be written (default-deny)
- **Path boundary:** `relative_to()` check prevents traversal outside cwd
- **Atomic writes:** temp file → validate → rename. On any failure, all temp files rolled back

## Tool-Use Agent

The LLM operates via tool calls, not output parsing. Available tools:

| Tool | Purpose | Limits |
|------|---------|--------|
| `write_file` | Create new file or full rewrite | Allowlist enforced, Python syntax-checked, max 100 lines for existing files |
| `edit_file` | Surgical line-range replacement | Staleness check, truncation guard |
| `read_file` | Read file contents | 500 line cap, numbered output |
| `run_command` | Execute shell command | 30s timeout, destructive patterns blocked |
| `lookup_docs` | Library documentation via /context7 | 30s timeout |
| `search_code` | Smart search: semantic if indexed, ripgrep fallback | 15s timeout, 50 match cap |
| `get_symbols` | AST symbols via /treesitter | 15s timeout |
| `research` | Deep research via /dogpile | **Once per task** (rate limited), 60s timeout |

### Tool Usage Guidelines

**File operations** (`write_file`, `edit_file`, `read_file`):
- Always `read_file` before `edit_file` — staleness detection rejects edits to files changed since last read
- Use `edit_file` for surgical changes to large files (>100 lines)
- Python files are `compile()`-checked before writing

**Search tools** (`search_code`, `get_symbols`):
- `search_code` is smart: checks for `.ingest-code.json` marker first
  - If indexed: queries `/memory` for semantic search (BM25 + cosine)
  - If not indexed: falls back to ripgrep pattern matching
  - Response includes `source: "memory"` or `source: "ripgrep"` to indicate which was used
- `get_symbols` extracts function/class signatures — use before editing unfamiliar files

**Research tools** (`lookup_docs`, `research`):
- `lookup_docs` for API reference (free, fast)
- `research` for complex questions (expensive, rate-limited to once per task)

See [PATTERNS.md](references/PATTERNS.md) for composition patterns with /orchestrate, /thunderdome, /classifier-lab, and subagent usage.

---

# In plan YAML:
tasks:
  - id: "3"
    title: "Fix auth bug"
    runner: "code-runner"
    backend: "codex"
    definition_of_done:
      command: "pytest tests/test_auth.py -q"
      assertion: "passed"
```

`/orchestrate` writes the task spec JSON and calls `./run.sh run spec.json`.
Code-runner loops until DoD passes. Project agent reviews `response.txt`.

### Pattern 2: /thunderdome → /code-runner (Competing Approaches)

Multiple backends race on the same task in isolated git worktrees. Best score wins.
Same pattern as `/classifier-lab` racing multiple backbones via `/switchboard`.

```bash
# /thunderdome spawns 3 competing /code-runner instances:
/thunderdome battle \
  --task "fix auth bug" \
  --dod "pytest tests/test_auth.py -q" \
  --contestants "codex,text,gemini" \
  --max-rounds 3
```

Each contestant:
- Gets its own git worktree (isolated, can't interfere)
- Runs `/code-runner` with the same task spec + DoD
- Self-improvement loop runs independently
- First to pass DoD wins, OR highest score after max rounds
- Winner's worktree merged back to main

This is the autoresearch pattern at the META level:
- **autoresearch** = one agent, many experiments, keep/discard per experiment
- **code-runner** = one backend, many rounds, keep/discard per round
- **thunderdome + code-runner** = many backends, each running many rounds, keep/discard per backend

```
/thunderdome
  ├─ worktree-A: /code-runner backend=codex
  │   ├─ Round 1: score=0.3 (KEEP)
  │   ├─ Round 2: score=0.7 (KEEP)
  │   └─ Round 3: score=1.0 (KEEP, DoD PASS) ← WINNER
  │
  ├─ worktree-B: /code-runner backend=text
  │   ├─ Round 1: score=0.4 (KEEP)
  │   ├─ Round 2: score=0.4 (DISCARD)
  │   └─ Round 3: score=0.6 (KEEP)
  │
  └─ worktree-C: /code-runner backend=gemini
      ├─ Round 1: score=0.2 (KEEP)
      └─ Round 2: score=0.0 (DISCARD, crash)
```

### Pattern 3: /plan → /orchestrate → /code-runner (Full Stack)

The standard pipeline for code projects:

```
/plan creates YAML with:
  - Task 1 (runner: local): install deps
  - Task 2 (runner: code-runner): write training pipeline code
  - Task 3 (runner: local): run training
  - Task 4 (runner: code-runner): fix any broken pipeline code
  - Task 5 (runner: local): verify all outputs

/orchestrate dispatches each task to its runner (async DAG scheduler).
/code-runner handles code authoring with self-improvement loop.
Local tasks handle deterministic shell commands.
All code-runner rounds store to llm_invocations for cross-session learning.
```

### Pattern 4: /code-runner as subagent (Bounded Worker)

A project agent delegates a bounded code task to /code-runner as a subagent.
The subagent runs the deterministic loop, the project agent reviews the output.

```python
# Project agent calls /code-runner for a specific fix
spec = {
    "task_id": "fix-empty-classes",
    "title": "Fix concurrent_run.py to resolve HF dataset label names",
    "prompt": "Read concurrent_run.py. The _write_ux_project function writes classCount: 0...",
    "backend": "text",
    "cwd": "/home/graham/workspace/experiments/pi-mono",
    "allowlist": [".pi/skills/classifier-lab/scripts/concurrent_run.py"],
    "definition_of_done": {
        "command": "python3 -c \"...assert data['classCount'] == 4...\"",
        "assertion": "OK"
    }
}
# Subagent runs the loop, project agent reviews response.txt
```

# WRONG: Fire and forget
./run.sh run spec.json
# Agent moves on without reading response.txt or result.json
# → This is how Codex wrote empty classes arrays (plan 12 incident)

# RIGHT: Run and review
./run.sh run spec.json
cat /tmp/output/task-id.result.json  # Check score, rounds, dod_passed
cat /tmp/output/task-id.response.txt # READ the actual code before accepting

# WRONG: Use /code-runner for design decisions
# "Decide whether to use REST or GraphQL and implement it"
# → Code-runner is a subagent. It runs and debugs. It doesn't architect.

# RIGHT: Use /code-runner for bounded implementation
# "Implement the REST endpoint for /api/users as specified in the plan"
# → Clear scope, clear DoD, clear file allowlist.

# WRONG: DoD that checks string existence
"command": "grep 'function_name' file.py"
# → LLM adds a comment with the function name and passes

# RIGHT: DoD that runs the code and checks output
"command": "python -c 'from module import function; result = function(test_input); assert result == expected'"
# → LLM must write code that actually works
```
