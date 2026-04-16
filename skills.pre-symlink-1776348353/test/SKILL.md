---
name: test
description: >
  Unified test runner for skills and packages. Auto-detects sanity.sh,
  pytest, vitest, lint.sh, and npm test — runs the right framework,
  returns structured JSON with figure_data for dashboard integration.
triggers:
  - test skill
  - run tests
  - run sanity
  - test all skills
  - sanity check
  - run pytest
  - run vitest
  - test this skill
  - check skill health
  - test runner
  - run all tests
  - test summary
provides:
  - test
composes:
  - task-monitor
---

# /test — Unified Test Runner

Auto-detects and runs the right test framework for any skill or package path.

## Commands

```bash
./run.sh run <path>                    # Run tests for a skill or package
./run.sh run <path> --json             # JSON output for automation
./run.sh all [--json]                  # Run all skill sanity checks
./run.sh all --include-pytest          # Also run pytest where available
./run.sh summary [--days 7]            # Show recent test history
```

## Detection

| File/Dir | Runner |
|----------|--------|
| `sanity.sh` | bash (exit 0/1) |
| `test_*.py` or `tests/` | pytest via `uv run` |
| `*.test.ts` or `vitest.config.ts` | vitest |
| `lint.sh` | bash linter |
| `package.json` with `test` script | `npm test` |

## JSON Output

```json
{
  "target": ".pi/skills/memory",
  "timestamp": "2026-02-28T17:00:00Z",
  "results": [
    {"type": "sanity", "status": "pass", "duration_s": 2.3, "output": "..."},
    {"type": "pytest", "status": "pass", "tests": 15, "passed": 14, "failed": 1, "duration_s": 8.1}
  ],
  "overall": "fail",
  "duration_s": 10.4,
  "figure_data": {
    "bar": {"metrics": {"sanity": 1, "pytest": 0}},
    "pie": {"Pass": 14, "Fail": 1}
  }
}
```

## Exit Codes

- `0` — all runners passed
- `1` — at least one runner failed
- `2` — warning (partial pass)

## Integration

- **skills-ci**: Can delegate to `/test run <skill> --json`
- **scheduler**: Nightly `test-all-sanity` job
- **orchestrate**: Quality gate calls `/test run <path>` before marking task complete
- **dashboard**: Reads `~/.pi/test/last_run.json` for test results
