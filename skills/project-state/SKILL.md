---
name: project-state
description: >
  Project state and readiness reporting in one command for Embry-style
  project checkouts and cleanup tails. Runs infrastructure metrics, /memory
  recall, doc-code drift, best-practices audit, current external research
  via /brave-search and /github-search, gap analysis, and post-cleanup
  readiness receipts.
triggers:
  - "project state"
  - "project status"
  - "system state"
  - "full status"
  - "comprehensive status"
  - "embry status"
  - "cleanup tail state"
  - "post cleanup state"
  - "project readiness report"
metadata:
  short-description: Project state and readiness reporting
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
provides:
  - project-state-report
  - readiness-report
  - cleanup-tail-state
composes:
  - service-status
  - data-audit
  - memory
  - assistant
  - brave-search
  - github-search
  - create-figure
  - task-monitor
  - checkpoint
complies:
  - best-practices-skills
  - best-practices-python
runtime_self_improvement: basic
taxonomy:
  - assessment
  - monitoring
  - operations
  - validation
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /project-state

Project state and readiness reporting for Embry-style project checkouts.

This skill is a reporter and readiness receipt generator. It does not delete
files, move files, rewrite code, authorize cleanup removals, or turn skipped
checks into success.

## Modes

| Mode | Flag | Phases | Time |
|------|------|--------|------|
| **Quick** | `--quick` | Phase 1 only | ~10s |
| **Standard** | (default) | Phases 1-4 + 6 | ~30s |
| **Full** | `--full` | All 6 phases, including Brave/GitHub/ArXiv research | ~2min |
| **Cached** | `--cached` | Return cached checkpoint if < 1 hour old, otherwise run live and save | ~1s (hit) / ~30s (miss) |
| **Force** | `--force` | Always run live, save checkpoint after | ~30s |
| **Cleanup Tail** | `report --cleanup-tail` | Load a cleanup receipt, run a bounded post-cleanup state snapshot, write readiness artifacts | ~30s |
| **Config Doctor** | `config doctor` | Check non-secret config without prompting | ~1s |

## Usage

```bash
# Standard report (infrastructure + memory + drift + best practices + gaps)
./run.sh report

# Quick infrastructure-only report
./run.sh report --quick

# Full report including competitive landscape via /dogpile
./run.sh report --full

# JSON for automation / piping to /create-figure
./run.sh report --json

# Write to file
./run.sh report --output state.md
./run.sh report --json --output state.json

# Use cached result if available and < 1 hour old
./run.sh report --cached

# Force live run and save checkpoint for next --cached call
./run.sh report --force

# Combine with other flags
./run.sh report --cached --json --output state.json
./run.sh report --force --quick

# Post-cleanup readiness receipt; never deletes or moves files
./run.sh report --cleanup-tail \
  --cleanup-receipt artifacts/cleanup/<run-id>/receipt.json \
  --json --output artifacts/cleanup/project_state_after.json

# Write readiness artifacts to an explicit directory
./run.sh cleanup-tail --cleanup-receipt artifacts/cleanup/<run-id>/receipt.json \
  --output-dir artifacts/project-state/readiness/<run-id> --json

# Non-interactive configuration check
./run.sh config doctor --json
```

## Readiness Report Contract

`cleanup-tail` writes a best-practices-skills-compatible readiness bundle:

```text
artifacts/project-state/readiness/<run-id>/
  report.json
  report.md
  index.html
```

`report.json` is the source of truth. The HTML page is only a view. The report
uses schema `skill.readiness_report.v1`, profile `cleanup-tail`, explicit
feature rows, case rows, `needs_attention`, and source receipt paths.

Release readiness is always `NOT_ESTABLISHED` for cleanup-tail because it is a
state/gap receipt, not project acceptance. If the cleanup receipt shows
moved/quarantined/manual-review items, the report marks `needs_attention` and
the safe default is to keep `.cleanup` intact until usage evidence is reviewed.

Cleanup-tail reports:

- repo dirty state after cleanup from `git status --porcelain`
- optional project-native sanity result from `--project-sanity-cmd`
- moved/kept/deleted/review-required path counts from the cleanup receipt
- best-practices commands recorded in the receipt or passed via
  `--best-practices-check`
- doc-code drift when the standard cleanup-tail profile runs
- stale/deprecated document findings surfaced through doc-code drift
- project knowledge presence and memory-sync status as explicit evidence gaps
- potential new gaps introduced by cleanup
- unresolved cleanup candidates

## Configuration

`./run.sh config doctor --json` is CI-safe and never prompts. Missing paths are
reported as `needs_attention` with a safe default. Use environment variables,
not hardcoded paths, when adapting this skill:

```bash
EMBRY_OS_ROOT=/path/to/project
PI_SKILLS_ROOT=/path/to/skills
```

## What It Reports

### Phase 1: Infrastructure (always runs)

| Section | Source | Data |
|---------|--------|------|
| **Daemons** | Unix socket health checks | Status of all 7 services |
| **Tests** | pytest --collect-only | Total count |
| **Cascade** | model_registry.json + shadow.jsonl | Tier status, trained models, shadow entries |
| **Training Pipeline** | ~/.pi/assistant/training_data/ | Labels per task, classifiers on disk |
| **Skills** | .pi/skills/ directory | Total count, SKILL.md/sanity.sh compliance |
| **Frontend** | apps/embry-ui/ | TSX component count, Rust file count |
| **Deploy** | services/systemd/ | Systemd unit count |
| **Cascade Wiring** | services/*-daemon/main.py | Which daemons have cascade integration |

### Phase 2: Memory Recall (standard + full)

Queries `/memory recall` for known features, competitive advantages, and known gaps.

### Phase 3: Doc-Code Drift (standard + full)

Scans docs for aspirational language (will, TODO, FIXME, planned, future, not yet) and stale file references.

### Phase 4: Best Practices (standard + full)

Scans for anti-patterns:
- **Python**: hardcoded secrets, bare except, hardcoded paths, print vs logger
- **React**: console.log, `:any` types
- **Skills**: missing YAML frontmatter, missing `provides` field

### Phase 5: Competitive Landscape (--full only)

Uses current retrieval lanes first: `/brave-search` for web results and
`/github-search` for repositories/issues. `/dogpile` is treated as a legacy
deep aggregator and should be used only when explicitly requested or when a
single broad multi-source research bundle is more important than freshness.

### Phase 6: Gap Analysis (always runs)

Synthesizes all previous phases into prioritized, actionable gaps with severity (critical/high/medium/low) and recommended actions.

## Project Knowledge

Current-state notes for this skill live in `docs/PROJECT_KNOWLEDGE.md`. Treat
that document as context, not proof. Readiness claims still require the
machine-readable report and command receipts.

## Visualization

After generating a report (especially with `--json`), offer to visualize key findings via `/create-figure`:

```bash
# Architecture diagram from project structure
create-figure architecture --project ./state.json --output arch.svg

# Gap severity distribution
create-figure metrics --input state.json --output gaps.png --type pie --title "Gap Severity"

# Skill health heatmap
create-figure heatmap --input state.json --output skill-health.png

# Full figure set from assess-compatible JSON
create-figure from-assess --input state.json --output-dir ./figures/
```

**When to offer:** After presenting the report, ask: "Want me to visualize any of these findings?"

## Common Mistakes

### WRONG: Running --full mode for a quick health check
```bash
./run.sh report --full  # takes ~2min, includes /dogpile competitive landscape
```

### RIGHT: Use --quick for fast checks, --cached for repeated queries
```bash
./run.sh report --quick   # ~10s, infrastructure only
./run.sh report --cached  # ~1s if cached within the hour
```

### WRONG: Not using --json when piping to other skills
```bash
./run.sh report > state.md  # markdown, not parseable by /create-figure
```

### RIGHT: Use --json for automation and visualization
```bash
./run.sh report --json --output state.json
create-figure from-assess --input state.json --output-dir ./figures/
```

### WRONG: Ignoring gap analysis (Phase 6) and only reading infrastructure
```bash
./run.sh report --quick  # misses doc-code drift, best practices violations, gaps
```

### RIGHT: Standard mode includes all critical phases
```bash
./run.sh report  # phases 1-4 + 6: infrastructure + memory + drift + practices + gaps
```

### WRONG: Treating cleanup-tail as cleanup authority
```bash
./run.sh report --cleanup-tail --cleanup-receipt artifacts/cleanup/run/receipt.json
# then delete .cleanup because the command exited zero
```

### RIGHT: Treat cleanup-tail as a state receipt only
```bash
./run.sh report --cleanup-tail --cleanup-receipt artifacts/cleanup/run/receipt.json --json
# inspect needs_attention and usage evidence before any cleanup deletion
```
