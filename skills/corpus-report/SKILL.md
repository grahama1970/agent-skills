---
name: corpus-report
description: >
  Report on the continuous PDF extraction learning system. Shows corpus statistics,
  S00/S04 section estimation quality, failure patterns, pipeline bottlenecks, and
  trends over time. Reads manifest.jsonl and pattern_registry.json from the 12TB
  extractor corpus.
allowed-tools: Bash, Read
triggers:
  - corpus report
  - corpus status
  - corpus stats
  - extraction quality
  - pipeline bottlenecks
  - corpus patterns
  - corpus trends
  - how is the corpus doing
metadata:
  short-description: Extractor corpus statistics, quality, and bottleneck analysis

provides:
  - corpus-report
composes:
  - create-figure
  - task-monitor
disciplines:
  - observability-operations
  - extraction
---

# Corpus Report

Report on the continuous PDF extraction learning system running on the 12TB drive.

## Quick Start

```bash
./run.sh                          # Quick summary (default)
./run.sh quality                  # S00/S04 ratio analysis
./run.sh patterns                 # Failure pattern registry
./run.sh bottlenecks --sample 20  # Pipeline stage timing
./run.sh trends --since 24        # Quality over last 24 hours
```

## Commands

| Command | Description |
|---------|-------------|
| `summary` | Total/completed/pending/failed, categories, presets, label distribution |
| `quality` | S00/S04 ratio histogram, worst offenders, accuracy percentages |
| `patterns` | Failure pattern frequency, affected files, cross-referenced with categories |
| `bottlenecks` | Per-stage timing aggregation, % of total pipeline time |
| `trends` | Quality metrics grouped by time windows |

## Options

| Flag | Commands | Description |
|------|----------|-------------|
| `--json` | All | Machine-readable JSON output |
| `--category TEXT` | All except bottlenecks | Filter by PDF category (arxiv, standards, etc.) |
| `--top N` | quality | Number of worst offenders (default: 10) |
| `--sample N` | bottlenecks | Limit result directory scanning |
| `--since HOURS` | trends | Only include recent PDFs |
| `--window HOURS` | trends | Time window size (default: 6) |

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `CORPUS_ROOT` | `/mnt/storage12tb/extractor_corpus` | Corpus root directory |

## Memory + Taxonomy Integration

The skill integrates with the shared memory and taxonomy systems via
`memory_integration.py` for longitudinal quality tracking:

- **Pre-hook (`recall_prior_reports`)**: Before generating a report, recalls prior
  corpus snapshots for trend comparison. Enables agents to detect quality drift
  over time without re-scanning.
- **Post-hook (`learn_report`)**: After generating the summary, stores a corpus
  report snapshot (total PDFs, success rate, failure patterns, top issues) to
  memory with taxonomy bridge tags.
- **Bridge keywords**: Precision, Resilience, Fragility, Corruption, Loyalty, Stealth
  (tuned to corpus quality domain).
- **Tags**: `["corpus_report", "drift_tracking"] + bridges`

Gracefully degrades if `common.memory_client` or `taxonomy/taxonomy.py` are unavailable.

## File Structure

```
corpus-report/
  SKILL.md                   # This file
  run.sh                     # Shell entry point
  sanity.sh                  # Sanity checks
  memory_integration.py      # Memory + Taxonomy hooks
  pyproject.toml             # Dependencies
  corpus_report/             # Python package
    __init__.py
    __main__.py
    cli.py                   # Typer CLI
    config.py                # Paths and constants
    formatters.py            # Rich/JSON output
    manifest.py              # Manifest loading and analysis
    models.py                # Data models
    patterns.py              # Failure pattern analysis
    timings.py               # Pipeline timing analysis
```

## Data Sources

- `metadata/manifest.jsonl` -- Per-PDF status, metrics, quality labels
- `metadata/pattern_registry.json` -- Detected failure patterns
- `results/*/timings_summary.json` -- Per-stage pipeline timing

## Visualization

After generating reports (especially with `--json`), offer to visualize via `/create-figure`:

```bash
# Quality trends over time
create-figure metrics --input corpus.json --output quality-trend.png --type line --title "Extraction Quality"

# Pipeline bottleneck breakdown
create-figure metrics --input corpus.json --output bottlenecks.png --type hbar --title "Pipeline Stage Timing"

# Failure pattern distribution
create-figure metrics --input corpus.json --output failures.png --type pie --title "Failure Patterns"
```

**When to offer:** After presenting quality or bottleneck data, ask: "Want me to chart the trends?"
