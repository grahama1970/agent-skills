# Code-Runner Project Knowledge

Last updated: 2026-05-07

## Current Understanding

Code-runner is a deterministic self-improvement loop for code authoring tasks.
It implements the autoresearch pattern: LLM proposes -> apply to disk -> T0 score -> keep/discard.

### Reliability Status (2026-05-07)

Current status:

- Patch-only reliability: Phase 2 adversarial tranche passing, not yet reliable.
- Complete-task reliability: initial hardening and rollback coverage started, not yet reliable.
- Legacy tests: stale monolithic tests are quarantined; useful assertions should be ported into `src/code_runner` unit tests or `tests/adversarial`.
- External benchmarks: not relevant yet; SWE-bench/Terminal-Bench should wait until the harness invariant suite is larger.

Phase 1 evidence:

- Imported the first adversarial tranche under `tests/adversarial`.
- Local compile gate passed for `src` and `tests/adversarial`.
- `tests/adversarial` passed three consecutive runs: 35/35 each run.
- Focused rebuilt-package/scillm checks passed: 5 passed, 18 skipped.
- Legacy `tests/test_backend_defaults.py` is skipped with a quarantine reason because it targets removed monolithic `code_runner.py` internals.

Hardening completed for the Phase 1 tranche:

- Reject orchestration-only fields inside `TaskSpec`.
- Reject absolute, empty, and traversal paths in `allowlist` and `read_context`.
- Reject `output_dir` inside a git source repo before artifact creation.
- Check symlink escapes with resolved path containment rather than string prefix checks.
- Keep real source cwd in runner internals while exposing only a worktree-substituted `CODE_RUNNER_SOURCE_CWD` to model-run commands.
- Fail closed before complete-task source apply when dirty source paths overlap the allowlist.
- Parse `git diff --cached --name-status` staged paths correctly before committing allowlisted files.

Phase 2 evidence:

- Added fake HTTP `/scillm` SSE tests that exercise the real `src/code_runner/scillm.py::stream_chat` path, including required headers, request shape, HTTP 400, missing terminal events, empty deltas, malformed JSON, fragmented tool call arguments, invalid tool arguments, and unknown tools.
- Added runtime fake-HTTP `/scillm` failure tests that verify diagnostic result writing, source snapshot preservation, and worktree cleanup.
- Added patch/hunk oracle tests for markdown hunk artifacts, new/deleted/renamed files, paths with spaces, unicode paths, `src` vs `src_evil`, mode-only changes, and binary diffs.
- Added six historical replay fixture contracts: dirty allowlist, DoD-from-source, wrong-cwd patch restore, patch-numstat wrong cwd, scillm HTTP 400, and false-green monolith.
- Local compile gate passed for `src` and `tests/adversarial`.
- `tests/adversarial` passed three consecutive Phase 2 runs at 75/75.

Phase 3 evidence:

- Committed Phase 2 checkpoint as `a3491d10` after rerunning the 75-test adversarial gate.
- Converted the six historical replay fixtures into executable tests that run the real code-runner `run_task` path with frozen fake `/scillm` behavior, expected result subsets, source snapshot checks, diagnostics, and worktree cleanup assertions.
- Added complete-task rollback/commit breadth tests for newly created, deleted, renamed, binary, and mode-only allowlisted changes, plus preservation of untracked and ignored nonallowlisted user work.
- The rollback matrix exposed and fixed a real rename rollback bug: `restore_allowlist` now restores tracked allowlisted paths from `HEAD` and cleans untracked allowlisted paths explicitly.
- Local compile gate passed for `src` and `tests/adversarial`.
- `tests/adversarial` passed at 90/90.

Phase 4 evidence:

- Added chaos/fault-injection cleanup tests around worktree creation, dependency mirroring, initial DoD, `/scillm` connection and timeout failures, tool execution, post-round DoD, patch export, source apply, source DoD, commit, and result JSON finalization.
- Added deterministic property-style path and patch tests for absolute paths, traversal, dot segments, `src` vs `src_evil` prefix tricks, spaces, unicode paths, symlink escapes, quoted git diff paths, and cwd-independent patch parsing.
- The chaos tranche exposed and fixed a real complete-task status bug: commit failures now make `run_task` fail instead of returning pass after source DoD succeeded.
- The patch property tranche exposed and fixed a real parser gap: `.hunk.md`/patch path extraction now handles quoted git diff paths.
- Mutation audit checks temporarily broke defenses and confirmed targeted tests failed:
  - removed nonzero-exit guarding for `contains:` DoD assertions; `test_contains_assertion_cannot_pass_with_nonzero_exit` failed.
  - weakened allowlist matching to string-prefix matching; segment-aware path tests and prefix-trick write denial failed.
  - removed `CODE_RUNNER_SOURCE_CWD` worktree substitution from `run_command`; source mutation blocking failed with source snapshot drift.
  - disabled `output_dir`-inside-source rejection; schema/preflight output-dir tests failed.
- Local compile gate passed for `src` and `tests/adversarial`.
- `tests/adversarial` passed at 125/125.

Phase 5 evidence:

- Added a marked `soak` suite under `tests/adversarial/soak` for repeated and parallel execution:
  - 100 serial patch-only runs against one source repo,
  - 100 patch-only runs with concurrency 4,
  - 50 fake HTTP `/scillm` failure runs,
  - 50 complete-task apply/rollback runs,
  - 25 complete-task `commit_on_success` runs with dirty nonallowlisted files present.
- Soak assertions cover source snapshot preservation for patch-only runs, no residual worktrees, valid result/status JSON artifacts, output artifact separation, rollback preservation of dirty/untracked/ignored user work, and commit allowlist behavior with dirty nonallowlisted files.
- Added a nightly/manual CI soak job while keeping the normal adversarial gate as `-m "not soak"`.
- Clean-shell blocking gate passed: `125 passed, 5 deselected`.
- Clean-shell soak gate passed: `5 passed, 125 deselected` in 92.57s.

Reliability status after Phase 5:

- Patch-only mode: strong reliability candidate. It has passed adversarial spine, fake HTTP `/scillm`, historical replay, chaos, mutation audit, property-style path/patch checks, and soak/parallel evidence.
- Complete-task mode: strong reliability candidate, still higher-risk than patch-only. It has passed rollback matrix, chaos checks, and repeated source-apply/rollback/commit soak evidence.
- Neither mode is declared final reliable yet; live E2E sanity and continued nightly soak history are still required.

Next reliability milestone:

- Add live E2E sanity tests behind a separate marker: patch-only smoke, complete-task smoke, and real `/scillm` request-shape smoke.
- Continue nightly/manual soak and record flake history before declaring reliability.
- Add rollback and commit breadth for symlink and additional dirty nonallowlisted source cases.
- Add cleanup tests for rollback failure, cleanup failure with manual leak recovery, and artifact-writing failures.

### Phase 1-3 Multica-Inspired Upgrades (2026-04)

Added normalized execution truth and web-based observability:

| Component | File | Purpose |
|-----------|------|---------|
| State machine | models.py | RunState, ReasonCode, EventType enums |
| Event emitter | event_emitter.py | Dual-write to events.jsonl + run.json |
| Run viewer | run_viewer.py | Single-run detail page (port 8765) |
| Fleet dashboard | fleet_dashboard.py | Multi-run monitoring (port 8766) |
| CLI wrapper | view.sh | Unified viewer commands |

**State Machine Design:**
- RunState: queued -> running -> {passed, failed, blocked, timed_out, crashed}
- preflight_failed is terminal (bad spec before execution)
- ReasonCode explains WHY a terminal state occurred (bad_dod, zero_write, max_rounds_exhausted)

**Event Flow:**
```
code_runner.py -> emitter.emit() -> events.jsonl (append) + run.json (snapshot)
                                         |
                                    run_viewer.py / fleet_dashboard.py
```


### scillm Token-Limit Policy Fix (2026-04-30)

`/scillm` rejects `max_tokens` with a 400 `scillm_policy_violation`; callers must omit `max_tokens` or use a provider-approved parameter. Code-runner previously sent `max_tokens` from `code_runner.py`, `tool_use.py`, and `diagnose.py`, which caused every round to fail before tool calls. The error classifier also mislabeled the policy violation as `context_overflow` because the response mentioned `max_tokens`. Code-runner now omits `max_tokens` and classifies this policy failure as a non-retryable format error.

### Reliability Hardening Lessons (2026-05-03)

Code-runner reliability work exposed several durable rules for future changes:

- SSE model calls must require both transport liveness and terminal semantics. Heartbeats and progress events are liveness only; a stream that ends without `[DONE]`/`finish_reason`, or without assistant content/tool calls, is a failed model call.
- Patch artifacts must be generated from actual git state in the disposable worktree, not from the tool loop's self-reported `written` list. The runner must compare real `git status`/diff output against the allowlist before scoring or exporting.
- Dependent code-runner tasks need a predecessor-applied baseline. Child patches must be exported relative to that baseline, and rollback must restore to the predecessor baseline before reapplying the best child patch.
- Test and verifier byproducts in disposable worktrees are expected. Untracked non-allowlist byproducts such as `__pycache__` can be cleaned inside the disposable worktree before scoring/export, but tracked non-allowlist modifications must fail closed.
- Orchestrate dependency semantics must be machine-checkable. If a downstream runner cannot consume code-runner patch artifacts, orchestrate should fail closed rather than run it against source `HEAD` and silently ignore predecessor work.
- Regression coverage needs unit tests for each failure mode plus one real composed smoke path. The acceptance smoke is `/orchestrate -> /code-runner -> /scillm` with codex/GPT-5.5 High, isolated worktree, patch artifact, source `HEAD` unchanged, and explicit handling for unavailable `test-lab`.

### Stabilized Orchestrate Boundary (2026-05-05)

The stable V1 path is deliberately narrow:

```
/orchestrate foreground YAML plan
  -> runner=code-runner
  -> isolated_worktree
  -> /scillm codex backend
  -> patch artifact only
  -> human/project-agent review
```

Current proof: 3/3 live disposable-repo E2E runs passed through
`/orchestrate -> /code-runner -> /scillm/codex` with:

- `result.json status=pass`
- `dod_passed=True`
- patch artifact exists
- `apply_to_source=False`
- source `HEAD` unchanged
- source worktree clean after completion

Passing sessions:

- `/mnt/storage12tb/artifacts/agent-skills/orchestrate/structured/session-1777991535`
- `/mnt/storage12tb/artifacts/agent-skills/orchestrate/structured/session-1777991579`
- `/mnt/storage12tb/artifacts/agent-skills/orchestrate/structured/session-1777991590`

This is evidence for the narrow patch-only path only. It is not evidence for
source apply, mandatory `/test-lab`, T2 review, patch chaining, parallelism,
dynamic skill context, or non-core runners.

### Feature Reintegration Queue (2026-05-05)

Keep these features outside the default code-runner/orchestrate path until each
has its own repeated real E2E proof:

| Feature | Current Status | Reintegration Bar |
|---------|----------------|-------------------|
| `/test-lab` mandatory blind eval | Optional/advisory in `/orchestrate` | Service can target arbitrary disposable repos; repeated pass/fail/connection-failure cases are recorded correctly |
| T2 review | Disabled by default in `/orchestrate` | Review artifacts are useful, non-flaky, and do not change source or task status incorrectly |
| Source apply / commit | Opt-in only | Isolated DoD passes before source mutation; source DoD passes; rollback works; source status is clean |
| Patch chaining | Disabled | Child patch is exported relative to predecessor-applied baseline; downstream failures are fail-closed |
| Parallel code-runner tasks | Disabled by default | Shared-cwd and disjoint-allowlist cases avoid git/worktree races over repeated runs |
| Skill context injection | Disabled by default | Curated context is frozen, bounded, auditable, and does not expose executable skill tools inside code-runner |
| Non-core runners | Disabled by default in `/orchestrate` | Each runner has a typed contract and failure accounting equivalent to code-runner/local |

### Project Knowledge Policy (2026-05-05)

`/project-knowledge` is now part of the code-runner skill composition, but only
as an outer coordination surface. It tracks stability evidence, disabled
features, and reintegration decisions. The code-runner process must not write to
project knowledge during a run; project agents should update this file after
material stability changes and sync it to memory when the memory service is
healthy.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Dual-write (events.jsonl + run.json) | events.jsonl for audit trail/ArangoDB, run.json for fast current-state reads |
| Web dashboards over TUI | Browser-based allows remote access, easy styling, no terminal dependencies |
| HTML escaping via `_esc()` helper | Prevent XSS from task titles, error messages, file paths |
| State transition validation logs warnings, doesn't block | Catch bugs without breaking execution during rollout |
| Fleet opens run_viewer via `?dir=` query param | Single run_viewer server handles any directory |
| `/project-knowledge` tracks stability/reintegration state | Keeps code-runner minimal while preserving current decisions for humans and agents |

## Open Questions

- [ ] Should events.jsonl be ingested to ArangoDB automatically or on-demand?
- [ ] Add TUI mode for headless servers (Phase 4)?
- [ ] Atomic file writes with locking for concurrent runs?
- [ ] Iterator-based reading for large events.jsonl files?
- [ ] What is the minimum repeated E2E count before each disabled feature can return to defaults?
- [ ] Should `/project-knowledge sync` be retried automatically when memory recall/upsert times out?

## Architecture Notes

**Viewer Architecture:**
- Fleet dashboard auto-refreshes via `<meta http-equiv="refresh">`
- Fleet click-through uses `?dir=/path/to/run` query param
- run_viewer.py parses query params via `urllib.parse`
- Both viewers use dark theme CSS matching code-runner's role as dev tooling

**Security:**
- All user-controlled data HTML-escaped before rendering
- Directory traversal limited by Path existence checks
- No authentication (local dev tool assumption)

## scillm Integration (2026-04)

Code-runner now properly integrates with scillm's new features:

| Feature | Implementation | Benefit |
|---------|---------------|---------|
| `X-Caller-Skill` header | Added to tool_use.py and code_runner.py | Cost tracking, debugging, error correlation |
| `scillm_metadata` | task_id, round, strategy, backend passed | Correlate rounds in llm_call_log |
| `reasoning_effort` | Forwarded as top-level request field | Codex/Claude actually receive requested reasoning effort |
| Canonical model names | `claude` → `claude-sonnet`, `gemini` → `gemini-flash`, `deepseek` → `text` | Matches current `/scillm` SKILL.md and avoids obsolete provider-specific aliases |

As of 2026-05-03, code-runner must send reasoning as top-level `reasoning_effort`, not only inside `scillm_metadata`. scillm maps Codex to provider-native `reasoning.effort`, returns `scillm_reasoning`, and logs `reasoning_forwarded` so ignored reasoning is visible.

**Source Grounding Verification (2026-04):**

Verifies that LLM fix responses actually reference the error they're supposed to fix.
Catches hallucinated fixes that don't address the actual problem.

| Component | File | Purpose |
|-----------|------|---------|
| `verify_fix_grounding()` | stderr_parser.py | Check if response references error terms |
| `grounding_reminder_prompt()` | stderr_parser.py | Generate reminder when grounding is low |
| `GroundingResult` | stderr_parser.py | Dataclass with score, matched/missing terms |

**Grounding Flow:**
```
round 2+ → error_ev from stderr → LLM fix response → verify_fix_grounding()
                                                           ↓
                                              grounding_score < 0.5?
                                                    ↓ yes
                                         grounding_reminder added to next prompt
                                         "IMPORTANT: Your fix must address the ACTUAL error..."
```

**Grounding Terms Extracted:**
- File names (e.g., `cache.py`)
- Error type keywords (e.g., `TypeError`, `ImportError`)
- Quoted identifiers from error messages
- Line numbers

**Future Opportunities:**
- [ ] Hedged calls (race codex + gemini, take first response)
- [ ] Streaming for long generations (avoid timeouts on complex fixes)

## Tool-Use Agent Expansion (2026-04)

Extended the tool-use agent with 4 new tools beyond the original 4 (write_file, edit_file, read_file, run_command):

| Tool | Backend | Purpose | Guardrails |
|------|---------|---------|------------|
| `lookup_docs` | /context7 | Library documentation lookup | 30s timeout |
| `search_code` | ripgrep (rg) | Fast codebase pattern search | 15s timeout, 50 match cap |
| `get_symbols` | /treesitter | AST symbol extraction | 15s timeout |
| `research` | /dogpile | Deep multi-source research | **Once per task**, 60s timeout, 2500 char output cap |

**Design decisions:**
- Ripgrep over grep: faster, respects .gitignore, better for code
- Smart routing in search_code: checks `.ingest-code.json` marker → semantic search via /memory if indexed, ripgrep fallback if not
- Research rate-limited: prevents runaway API costs during self-improvement loops
- All tools return structured JSON via `_tool_result()` helper for consistent parsing

**Semantic search integration:**
- `/ingest-code` writes `.ingest-code.json` marker after successful scan
- `search_code` checks for marker in cwd
- If found: queries `/memory recall` with codebase-scoped tags
- If confidence > 0.3: returns semantic results with `source: "memory"`
- Otherwise: falls back to ripgrep with `source: "ripgrep"`

**Implementation:**
- Tool definitions in `TOOLS` list (OpenAI function format)
- Execute handlers in `execute_tool()` function
- `_research_used` global flag tracks rate limit per session

## Related Skills

- `/orchestrate` - Dispatches tasks to code-runner
- `/project-knowledge` - Tracks code-runner stability evidence and feature reintegration status
- `/thunderdome` - Races multiple backends via code-runner in worktrees
- `/scillm` - LLM backend for fix proposals (see scillm Integration section)
- `/memory` - Cross-session learning from llm_invocations
- `/treesitter` - Deterministic code context extraction
