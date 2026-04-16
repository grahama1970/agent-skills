# Code-Runner Project Knowledge

Last updated: 2026-04-14

## Current Understanding

Code-runner is a deterministic self-improvement loop for code authoring tasks.
It implements the autoresearch pattern: LLM proposes -> apply to disk -> T0 score -> keep/discard.

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

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Dual-write (events.jsonl + run.json) | events.jsonl for audit trail/ArangoDB, run.json for fast current-state reads |
| Web dashboards over TUI | Browser-based allows remote access, easy styling, no terminal dependencies |
| HTML escaping via `_esc()` helper | Prevent XSS from task titles, error messages, file paths |
| State transition validation logs warnings, doesn't block | Catch bugs without breaking execution during rollout |
| Fleet opens run_viewer via `?dir=` query param | Single run_viewer server handles any directory |

## Open Questions

- [ ] Should events.jsonl be ingested to ArangoDB automatically or on-demand?
- [ ] Add TUI mode for headless servers (Phase 4)?
- [ ] Atomic file writes with locking for concurrent runs?
- [ ] Iterator-based reading for large events.jsonl files?

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
| Fixed model name | `claude` → `claude-sonnet-4-6` | Was `text-claude` (invalid) |

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
- `/thunderdome` - Races multiple backends via code-runner in worktrees
- `/scillm` - LLM backend for fix proposals (see scillm Integration section)
- `/memory` - Cross-session learning from llm_invocations
- `/treesitter` - Deterministic code context extraction
