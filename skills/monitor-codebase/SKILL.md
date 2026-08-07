---
name: monitor-codebase
description: >
  Continuous codebase health monitoring for all registered projects.
  Composes project-state, cleanup, ingest-code, quality-checks, skills-ci,
  dogpile research, and orchestrated fix verification.
triggers:
  - monitor codebase
  - codebase health
  - scan all projects
  - project health check
  - best practices audit
allowed-tools:
  - Bash
  - Read
metadata:
  short-description: Continuous codebase health monitor
provides:
  - codebase-monitoring
composes:
  - project-state
  - cleanup
  - ingest-code
  - security-scan
  - skills-ci
  - treesitter
  - embedding
  - memory
  - dogpile
  - orchestrate
  - code-runner
  - scheduler
  - task-monitor
  - best-practices-python
  - best-practices-rust
  - best-practices-react
  - best-practices-prompt
  - best-practices-kde
  - best-practices-skills
  - best-practices-streamdeck
  - review-prompt
  - create-figure
taxonomy:
  - precision
  - resilience
  - fragility
disciplines:
  - observability-operations
  - evaluation-quality
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# monitor-codebase

Continuous codebase health monitoring for all registered projects. Scans for
violations, researches fixes, runs isolated remediation workflows, and tracks
health trends over time.

## Commands

| Command | Description |
|---------|-------------|
| `scan <project>` | Scan a single registered project (full or light based on git changes) |
| `scan --all` | Scan every project in the registry |
| `scan --all --force` | Force full scan on all projects (ignore change detection) |
| `scan <project> --fix` | Scan and run an orchestrated fix workflow for violations |
| `audit <project> [--base REF]` | Run a changed-file audit and emit a Fallow-style `pass`/`warn`/`fail` verdict |
| `cache-state [project...] [--force]` | Refresh project-state only for projects with new commits |
| `report [project]` | Show latest findings from memory |
| `create-pr [--base main] [--title ...]` | Create PR with violation summary from latest nightly |
| `pr-comment <pr_number> [project]` | Add violation summary comment to an existing PR |
| `visualize <project> [--format svg\|png\|pdf]` | Generate dependency graph + health charts via /create-figure |
| `schedule` | Register nightly scan with /scheduler |

## Machine-Readable Finding Contract

Scanner outputs are an automation contract. Human prose may change, but JSON
fields used by `/orchestrate`, `/code-runner`, dashboards, and PR comments must
stay stable. New fields are additive. Breaking field changes require a
`schema_version` bump.

Full scans and audits emit:

```json
{
  "schema_version": 2,
  "version": "monitor-codebase-fallow-v2",
  "command": "aggregate",
  "project": "pi-mono",
  "path": "/path/to/project",
  "timestamp": "20260429T120000Z",
  "verdict": "warn",
  "summary": {
    "total_findings": 1,
    "total_issues": 1,
    "by_source": {"quality_checks": 1},
    "by_rule": {"mock-only-tests": 1},
    "by_severity": {"warn": 1}
  },
  "findings": [
    {
      "finding_id": "mock-only-tests:tests/test_api.py:0",
      "rule": "mock-only-tests",
      "source": "quality_checks",
      "file": "tests/test_api.py",
      "line": 0,
      "message": "All tests use mocks but no sanity.sh...",
      "severity": "warn",
      "confidence": 0.85,
      "evidence": {
        "source": "monitor-codebase",
        "detector": "quality_checks.py"
      },
      "actions": [
        {
          "type": "add-real-smoke-test",
          "auto_fixable": false,
          "runner": "code-runner",
          "description": "Add a non-mocked sanity or smoke test..."
        },
        {
          "type": "suppress",
          "auto_fixable": false,
          "description": "Document why mocked tests are sufficient..."
        }
      ],
      "remediation_route": {
        "runner": "code-runner",
        "confidence": 0.72,
        "reason": "Bounded test-quality finding with executable verification",
        "allowlist": ["tests/", "sanity.sh"],
        "definition_of_done": {
          "command": "python -m compileall -q tests",
          "assertion": "exit_code == 0"
        }
      }
    }
  ],
  "sources": {
    "quality_checks": {},
    "embedding_coverage": {}
  }
}
```

Required finding fields:

| Field | Meaning |
|---|---|
| `finding_id` | Stable identity: `rule:file:line` |
| `rule` | Stable rule ID |
| `severity` | `info`, `warn`, `error`, or `critical` |
| `confidence` | Detector confidence from 0.0 to 1.0 |
| `evidence` | Structured detector/source context |
| `actions[]` | Machine-actionable next steps, including suppressions |
| `remediation_route` | Suggested runner and DoD when automation is appropriate |

## Runner Selection

`monitor-codebase` detects and routes; it does not make open-ended code changes
inside scanners.

| Runner | Use When | Do Not Use When |
|---|---|---|
| `local` | The action is deterministic shell work or report formatting | The task needs code judgment |
| `code-runner` | File scope is bounded and the DoD is executable | The task is architectural or exploratory |
| `subagent-runner` | A real PTY session, transcript, or human intervention is needed | A deterministic DoD and allowlist are already known |
| `review-prompt` | Prompt template needs multi-model prompt review or payload repair | The finding is ordinary source code, not prompt quality |
| `human-review` | Static evidence is insufficient or deletion may remove runtime behavior | A mechanical change can be verified safely |

Routes are recommendations. The project agent must still review
`code-runner`/`subagent-runner` artifacts before accepting changes.

## Audit vs Full Scan

Full scans measure project health and trend drift. Changed-file audits should be
used for PRs and agent-generated patches. Audit output should reuse the same
finding contract and return a top-level `verdict` of `pass`, `warn`, or `fail`.

`audit <project> [--base REF]` runs the deterministic scanners, filters
file-scoped findings to files changed against the base ref, preserves repo-level
findings such as embedding coverage, and writes the same schema as full scans
with `command: "audit"`, `changed_files`, `changed_files_count`, `base_ref`, and
`head_sha`.

## Change Detection

Projects are tracked by git HEAD hash. On `scan --all`:
- **Changed projects** → full 11-step scan
- **Unchanged projects** → light scan (project-state only)
- **`--force`** → full scan regardless of changes

## Full Scan Pipeline (11 steps, for changed projects)

| Step | Skill/Module | What It Does |
|------|-------------|-------------|
| 1 | `/project-state` | Baseline health snapshot (JSON) |
| 2 | `/cleanup --dry-run` | Dead files, stale docs, junk artifacts |
| 3 | `run_best_practices_checks()` | Grep-based: missing run.sh/sanity.sh for skills plus TypeScript/React/Rust/KDE/StreamDeck patterns |
| 4 | `quality_checks.py` | AST-based and file-content checks: Python, TypeScript, Rust, prompt templates, inline prompts, regex classifiers, tests, hardcoded paths, bespoke AQL |
| 4.5 | `/security-scan` | Secrets detection (gitleaks), dependency vulnerabilities (pip-audit/trivy), SAST (Semgrep) |
| 5 | `autofix_docstrings.py` | Auto-generate missing docstrings via /treesitter + /scillm (**--fix only**, scan is read-only) |
| 6 | `/ingest-code --treesitter` | CWE scan + treesitter symbol extraction + semantic embedding via `/memory learn` (embedding-at-insert contract) |
| 6.1 | `embedding_coverage.py` | Compare expected source files against Qdrant-synced `code_symbols` records for the `monitor-<project>` scope |
| 7 | `/skills-ci` | Full skills-ci scan (only if project has skills/ or .pi/skills/ dir) |
| 8 | `/dogpile` | Research improvements for top violations (only if >5 issues found) |
| 9 | `fallow_contract.py aggregate` + `/memory learn` | Normalize all scan sources into `findings[]`, compute `verdict`, persist for trend tracking |
| 9.5 | Trend + anomaly detection | Compare with rolling history (z-score), classify as `REGRESSION`, `IMPROVED`, `STABLE`, or `SPIKE` |
| 10 | `/orchestrate` + `/code-runner` | **--fix only**: generate a fix task file and run the remediation workflow |

## Light Scan (for unchanged projects)

| Step | Skill | What It Does |
|------|-------|-------------|
| 1 | `/project-state` | Health snapshot refresh |

No violations scanning, no dogpile, no code modification. Just refreshes the state.

## Quality Checks (Step 4)

`quality_checks.py` runs AST-based and conservative file-content analysis across
Python, TypeScript/JavaScript, React, Rust, and prompt templates. It is a
monitor, not a replacement for each language's compiler, formatter, prompt
review loop, or best-practices skill.

| Check | Rule | What It Detects |
|-------|------|-----------------|
| Banned imports | `use-loguru`, `use-httpx`, `use-typer` | `import logging/requests/argparse` via AST |
| File length | `max-800-lines` | Python files >800 lines |
| Inline prompts | `inline-prompt` | LLM prompts in string literals (>200 chars, 2+ indicators) |
| Regex classifier | `regex-classifier` | Functions with 3+ regex calls + 2+ branches |
| Hardcoded paths | `hardcoded-skill-path` | `~/.pi/skills/` instead of SKILLS_DIR |
| Shell AQL | `shell-aql` | Raw AQL in .sh files (memory project exempt) |
| Python AQL | `python-bespoke-aql` | Raw AQL in .py files (memory project exempt) |
| Handwritten tests | `handwritten-tests` | test_*.py without test-lab markers |
| Mock-only tests | `mock-only-tests` | All tests use mocks, no sanity.sh |
| TypeScript `any` | `typescript-any-type` | `: any`, `as any`, and `<any>` casts |
| TypeScript inline imports | `typescript-inline-import` | `import(...)` in code or type positions |
| React/TS barrel imports | `typescript-barrel-import` | Imports from `index`/directory barrels in JSX/TSX |
| Rust unwraps | `rust-unwrap` | `.unwrap()` in non-test Rust source |
| Rust debug output | `rust-debug-output` | `dbg!` or `eprintln!` in non-test Rust source |
| Prompt rationale | `prompt-missing-rationale` | Prompt files without best-practices-prompt rationale header |
| Prompt vague words | `prompt-weasel-word` | Vague prompt terms such as `relevant`, `ensure`, `appropriate` |
| Prompt output contract | `prompt-missing-output-format` | Prompt files without an explicit output format/schema |
| Prompt review payload | `prompt-missing-review-payload` | System/user prompt pairs missing `review/*_payload.txt` |

Each violation is normalized by `fallow_contract.py` into Fallow-style
`actions[]` and a suggested `remediation_route` so downstream automation can
decide whether to use `code-runner`, `subagent-runner`, `review-prompt`, local
shell, or human review.

## Embedding Coverage

`monitor-codebase` must verify that `/ingest-code` produced usable semantic
coverage for registered projects. Full scans run `/ingest-code rescan
--treesitter --scope monitor-<project>` and then run `embedding_coverage.py`.

The coverage audit:
- collects expected script files using the same broad language scope as
  `/ingest-code` (`.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.rs`, `.go`, `.java`,
  `.c`, `.cpp`, `.h`, `.hpp`, `.rb`, `.php`, `.swift`, `.kt`, `.scala`)
- respects `.monitor-codebase.json` include/exclude directories and git ignored
  files
- reads memory's `code_symbols` collection through `/memory /list`
- counts a file as embedded only when at least one `code_symbols` record for
  that file has `semantic_sync_state: "synced"` and a `qdrant_point_id`

Coverage output is stored under `embedding_coverage` in the scan report and
summarized with `embedding_coverage_pct`, `embedding_missing_files`, and
`embedding_unsynced_files`. This is intentionally stricter than
`/ingest-code --verify-embeddings`, which is only a recall spot-check.

When coverage is not clean, `fallow_contract.py` emits normalized
`embedding-missing-file`, `embedding-unsynced-file`, or
`embedding-coverage-unavailable` findings.

## Best-Practices Mapping

| File Pattern | Best-Practices Skill | Key Checks |
|---|---|---|
| `*/skills/*/SKILL.md` | best-practices-skills | run.sh, sanity.sh, frontmatter |
| `*.py` | best-practices-python | package layout, uv, loguru/httpx/typer, test sanity |
| `*.rs`, `Cargo.toml` | best-practices-rust | error handling, tracing, cargo workspace, tests |
| `*.ts`, `*.tsx`, `*.js`, `*.jsx` | best-practices-react | React/Next.js performance and bundle patterns |
| `prompts/**/*`, `*prompt*.md`, `*prompt*.txt` | best-practices-prompt, review-prompt | rationale headers, concrete output contracts, review payloads |
| `*/plasmoids/*`, `*/kde-*` | best-practices-kde | KDE/Plasma patterns |
| `*/streamdeck/*` | best-practices-streamdeck | StreamDeck patterns |

## Fix Workflow

When `scan --fix` finds violations:

1. Generates `0N_FIX_TASKS.md` with violation details and fix instructions
2. Runs `/dogpile search` for fix strategy when the findings need external research
3. Uses `/orchestrate` to execute the remediation plan
4. Uses `/code-runner` to implement and iterate on fixes inside the workflow
5. Runs verification gates before accepting the result
6. Persists the final outcome for later trend analysis

## Project Scoping

Each project can have `.monitor-codebase.json` to control scan scope:
