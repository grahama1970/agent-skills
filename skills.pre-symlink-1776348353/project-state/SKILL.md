---
name: project-state
description: >
  Comprehensive Embry OS project state in one command.
  6-phase assessment: infrastructure metrics, /memory recall, doc-code drift,
  best practices audit, competitive landscape (/dogpile), and gap analysis.
  Like /assess but automated and repeatable.
triggers:
  - "project state"
  - "project status"
  - "system state"
  - "full status"
  - "comprehensive status"
  - "embry status"
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
provides:
  - project-state-report
composes:
  - service-status
  - data-audit
  - memory
  - assistant
  - dogpile
  - create-figure
  - task-monitor
  - checkpoint
taxonomy:
  - assessment
  - monitoring
  - operations
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /project-state

Comprehensive Embry OS project state — 6-phase assessment in one command.

## Modes

| Mode | Flag | Phases | Time |
|------|------|--------|------|
| **Quick** | `--quick` | Phase 1 only | ~10s |
| **Standard** | (default) | Phases 1-4 + 6 | ~30s |
| **Full** | `--full` | All 6 phases | ~2min |
| **Cached** | `--cached` | Return cached checkpoint if < 1 hour old, otherwise run live and save | ~1s (hit) / ~30s (miss) |
| **Force** | `--force` | Always run live, save checkpoint after | ~30s |

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

Queries `/dogpile` for defense manufacturing compliance AI and MES/digital twin landscape.

### Phase 6: Gap Analysis (always runs)

Synthesizes all previous phases into prioritized, actionable gaps with severity (critical/high/medium/low) and recommended actions.

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
