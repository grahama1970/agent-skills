# Code Review Request: evidence_case.py + review_question.py amendments

## Context

New `evidence-case` command added to the `review-question` skill.  This is a 5-gate deterministic pre-validation pipeline that proves whether a SPARTA security question is answerable BEFORE any LLM persona touches it.

## Strict Review Criteria

You MUST evaluate against ALL of the following best-practice rulesets and produce concrete, actionable findings with code-level fixes.

### /best-practices-python Rules (HARD GATES)

1. **conventions-pyproject-deps-complete** — Every import in `.py` files MUST have a corresponding `[project.dependencies]` entry in pyproject.toml. Missing deps = `ModuleNotFoundError` after venv recreation.
2. **conventions-loguru** — Use Loguru for logging, not stdlib `logging`.
3. **conventions-typer-cli** — Use Typer for CLI, not argparse/click.
4. **conventions-httpx** — Use httpx for HTTP, not requests/urllib.
5. **correctness-no-bare-except** — No bare `except:` or overly broad `except Exception:`.
6. **correctness-return-types** — Functions should have return type annotations.
7. **correctness-avoid-mutable-defaults** — No mutable default arguments.
8. **perf-avoid-n2** — No O(n^2) algorithms where O(n log n) or O(n) is possible.
9. **security-validate-untrusted-input** — Validate all untrusted input (user questions, subprocess output).
10. **testing-non-mocked-sanity** — Sanity tests are mandatory.
11. **Module docstrings required** — Every module needs a docstring.
12. **Max 800 LOC per file** — No file should exceed 800 lines.
13. **Functions over classes** — Prefer functions to classes where possible.

### /best-practices-skills Rules (HARD GATES)

1. **ArangoDB Access (NON-NEGOTIABLE)** — `/memory` is the ONLY skill that accesses ArangoDB directly. All other skills MUST use `memory/run.sh` subcommands. NEVER: `from arango import ArangoClient`. Verify evidence_case.py does NOT import python-arango directly.
2. **Storage Policy** — Heavy artifacts on `/mnt/storage12tb/`, not root NVMe.
3. **SKILL.md frontmatter** — Required fields: name, description, triggers, provides, composes. No code fences around frontmatter.
4. **Task-Monitor Integration** — Skills should report to `/task-monitor`.
5. **Anti-Patterns** — No argparse/click, no reimplementing helper skills, no missing dotenv loading.
6. **Composition** — Must delegate to existing skills, not rebuild capabilities.

### Architecture & Anti-Silo Rules

1. **ALL LLM calls go through /scillm** — NEVER use openai client directly.
2. **ALL retrieval goes through /memory** — No standalone AQL, no bespoke search pipelines.
3. **Entity extraction uses IntentMapper** via `/memory intent`, not custom regex (regex is fallback only).
4. **ArangoDB database is ALWAYS `memory`** — never `lessons`.

## Files to Review

### evidence_case.py (NEW — ~500 lines)
```
/home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/evidence_case.py
```

### review_question.py (MODIFIED — added evidence-case command)
```
/home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/review_question.py
```

### SKILL.md (MODIFIED — added evidence-case triggers/composes)
```
/home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/SKILL.md
```

### pyproject.toml (EXISTING — check deps completeness)
```
/home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/pyproject.toml
```

## Review Deliverables Required

For each finding:
1. **Severity**: CRITICAL / HIGH / MEDIUM / LOW
2. **Rule violated**: Which best-practice rule
3. **Location**: file:line
4. **Current code**: What's wrong
5. **Fixed code**: Exact replacement
6. **Rationale**: Why this matters

At the end, provide:
- A summary table of all findings by severity
- A unified diff patch that fixes ALL issues
- Specific assessment: does this code comply with the anti-silo rule?
- Performance assessment: are there O(n^2) patterns?
- Security assessment: is untrusted input validated?

## Additional Context

- The `_memory_cmd()`, `_memory_count()`, `_memory_recall()`, `_memory_trace()` helpers call `/memory run.sh` via subprocess — this is the CORRECT anti-silo pattern.
- `_regex_entity_extract()` is a FALLBACK only, used when `/memory intent` is unavailable.
- The `_find_path()` function does 1-hop check via `/memory count`, then 2-hop via `/memory trace` — verify this is efficient.
- `_connected_components()` is a pure BFS algorithm — verify no O(n^2) issue with the entity pair checking in Gate 3.
- Shadow-lego logging to `shadow.jsonl` is best-effort (silent failures OK).
- The pipeline supports recursive decomposition (sub-cases) with max depth control.
