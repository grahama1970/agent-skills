---
name: table-lab
description: >
  Iteratively tune Camelot table extraction parameters for PDFs.
  v2: Convergence loop, watchdog monitoring, Federated Taxonomy
  bridge tagging, batch corpus tuning with checkpoint/resume,
  corpus-report data contract, and task-monitor integration.
allowed-tools: Bash, Read, Write
triggers:
  - debug table
  - tune table extraction
  - table settings
  - camelot settings
  - fix table extraction
  - table fragmentation
  - why are tables broken
  - batch tune tables
  - table watchdog
metadata:
  short-description: Iterative Camelot parameter tuning with convergence, watchdog, and taxonomy

provides:
  - table-lab
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - extraction
  - evaluation-quality
---

# table-lab v2

Iteratively tune Camelot table extraction parameters for PDFs. Supports
single-PDF tuning with convergence loop, batch corpus tuning with watchdog
monitoring, Federated Taxonomy bridge tagging, and corpus-report integration.

## Agent Workflow

When invoked, follow this sequence:

### 1. Memory Recall (MANDATORY FIRST STEP)

```bash
/memory recall "table extraction settings for <category> <preset>"
```

If memory returns a known-good configuration, use it as the starting baseline.

### 2. Single PDF Tuning

```bash
# Quick dry-run to see which pages have tables
./run.sh tune <pdf> --dry-run

# Full sweep with convergence refinement
./run.sh tune <pdf> --converge --preset requirements_spec --category Engineering

# Manual probe for specific parameters
./run.sh probe <pdf> --flavor lattice --line-scale 25 --page 5
```

The `--converge` flag enables iterative refinement: if the initial sweep finds
fragmentation > 0, it builds a refined parameter grid centered on the best
result and re-runs (up to `--max-iterations` times).

### 3. Batch Corpus Tuning (with Watchdog)

```bash
./run.sh tune-corpus /mnt/storage12tb/extractor_corpus/results \
  --glob "**/*_clean.pdf" \
  --json-stream \
  --task-name my_batch_tune
```

The batch tuner:
1. Discovers PDFs matching the glob pattern
2. Resumes from checkpoint (skip already-tuned PDFs)
3. Resolves preset/category from `pipeline_context.json`
4. Runs convergence tuning per PDF
5. Tags results with Federated Taxonomy bridge attributes
6. Monitors quality via watchdog (pause-assess-diagnose-resume)
7. Writes to corpus-report data contract (NDJSON + manifest patching)
8. Registers with task-monitor for cross-skill visibility

### 4. Review and Export

```bash
./run.sh show                              # View all stored hints
./run.sh watchdog --task-name my_batch     # Check batch progress
./run.sh apply --to-corpus                 # Export to S05
```

### 5. Memory Learn

```bash
/memory learn --problem "table extraction settings for <category> <preset>" \
  --solution "flavor=<f> line_scale=<ls> edge_tol=<et>. Bridge tags: Precision, Resilience."
```

## Commands

| Command | Description |
|---------|-------------|
| `tune <pdf>` | Sweep parameter grid (+ optional convergence) |
| `probe <pdf>` | Single extraction attempt with specific params |
| `show` | Display stored hints |
| `apply` | Export hints to corpus metadata for S05 |
| `tune-corpus <dir>` | Batch tune with watchdog monitoring |
| `watchdog` | Show checkpoint and watchdog status |

## Key Options

| Flag | Commands | Description |
|------|----------|-------------|
| `--converge` | tune | Enable iterative refinement loop |
| `--max-iterations N` | tune, tune-corpus | Max convergence iterations (default 3) |
| `--json-stream` | tune-corpus | NDJSON output per PDF |
| `--no-resume` | tune-corpus | Ignore checkpoint, start fresh |
| `--task-name NAME` | tune-corpus, watchdog | Checkpoint/monitor name |
| `--glob PATTERN` | tune-corpus | PDF search pattern |
| `--preset P` | tune, show, apply | S00 preset name |
| `--category C` | tune, show, apply | PDF category |
| `--to-corpus` | apply | Write to CORPUS_ROOT/metadata |
| `--json` | all | Machine-readable JSON output |

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `CORPUS_ROOT` | `/mnt/storage12tb/extractor_corpus` | Corpus root path |
| `DEBUG_TABLE_DATA` | `~/.pi/table-lab` | Persistent data dir |
| `WATCHDOG_WARN_FRAGMENTATION_RATE` | `0.65` | Warn if frag rate exceeds |
| `WATCHDOG_STOP_FRAGMENTATION_RATE` | `0.55` | Stop if frag rate exceeds |
| `CIRCUIT_BREAKER_MAX_FAILURES` | `5` | Stop after N consecutive failures |
| `MAX_CONVERGENCE_ITERATIONS` | `3` | Max refinement iterations |
| `CONVERGENCE_SCORE_DELTA` | `2.0` | Min score improvement to continue |

## Watchdog Thresholds

The watchdog implements **Pause-Assess-Diagnose-Resume** from batch-quality:

| Metric | Warning | Stop |
|--------|---------|------|
| Fragmentation rate | >= 65% of PDFs | > 55% of PDFs |
| Consecutive failures | 3 | 5 |

Assessment requires minimum 3 PDFs. State is logged every 5 PDFs.

## Federated Taxonomy Bridge Tags

Each tuning result is tagged with Bridge Attributes (Tier 0) for multi-hop
graph traversal in ArangoDB:

| Bridge Attribute | Signal | Enables |
|-----------------|--------|---------|
| **Precision** | frag=0, cells>=10 | "Find all precisely-extracted docs" |
| **Resilience** | frag=0 (consistent) | "Find resilient extraction patterns" |
| **Fragility** | frag>5 | "Find all fragile documents" |
| **Corruption** | All strategies failed | "Find corrupted documents" |

Tags are stored in hint data and written to the corpus-report NDJSON contract.

## Data Flow

```
                                    +--> ~/.pi/table-lab/hints/
                                    |
tune / tune-corpus  ----------------+--> ~/.pi/table-lab/checkpoints/
                                    |
                                    +--> CORPUS_ROOT/metadata/table_hints.json
                                    |       (S05 reads at extraction time)
                                    |
                                    +--> CORPUS_ROOT/metadata/table_tune_results.jsonl
                                    |       (corpus-report data contract)
                                    |
                                    +--> CORPUS_ROOT/metadata/manifest.jsonl
                                    |       (patched with s05_tune_* fields)
                                    |
                                    +--> ~/.pi/task-monitor/registry.json
                                            (cross-skill visibility)
```

## corpus-report Data Contract

Each tune result appends to `CORPUS_ROOT/metadata/table_tune_results.jsonl`:

```json
{
  "pdf_name": "NIST.SP.800-53B_clean.pdf",
  "preset": "requirements_spec",
  "category": "Engineering",
  "best_flavor": "stream",
  "best_edge_tol": 25,
  "fragmentation": 0,
  "cell_count": 17,
  "bridge_tags": ["Precision", "Resilience"],
  "iterations": 1,
  "converged": true
}
```

Also patches the corresponding `manifest.jsonl` entry with:
- `s05_tune_strategy`: best flavor + params
- `s05_tune_fragmentation`: fragmentation score
- `s05_tune_bridge_tags`: bridge attribute list
