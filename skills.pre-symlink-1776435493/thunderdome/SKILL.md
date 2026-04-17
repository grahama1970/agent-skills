---
name: thunderdome
description: >
  N-way concurrent tournament convergence skill. Dispatches N competing strategies
  via /subagent-service in parallel, scores results against a pluggable metric,
  diagnoses failures with persona reviewers, /dogpile-researches on combined failure,
  and iterates until convergence or exhaustion. Manifest-driven (YAML).
  Two strategies enter, one strategy leaves.
  Use when: self-improvement loop, tournament, convergence, compete strategies,
  concurrent training, parallel approaches, best-of-N, arena.

triggers:
  - thunderdome
  - tournament
  - run tournament
  - compete strategies
  - convergence loop
  - self-improvement loop
  - arena
  - best of N
  - concurrent strategies
  - parallel tournament

allowed-tools: [Bash, Read, Write, Glob, Grep]

metadata:
  short-description: "N-way concurrent tournament with convergence gates"
  author: "Graham Anderson"
  version: "1.0.0"

provides:
  - concurrent-tournament
  - convergence-loop
  - competitive-selection

composes:
  - code-runner
  - dogpile
  - memory
  - classifier-lab
  - task-monitor

taxonomy:
  - precision
  - resilience
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /thunderdome

Two strategies enter, one strategy leaves.

N-way concurrent tournament that converges on a quality gate. Dispatches competing
strategies via `/subagent-service`, scores by a pluggable metric, diagnoses failures
with persona reviewers, and `/dogpile`-researches on combined failure.

## Quick Start

```bash
# Run a tournament from a manifest
./run.sh run examples/classifier-table-merge.yaml

# Dry run (validate manifest, show plan, don't execute)
./run.sh run examples/classifier-table-merge.yaml --dry-run

# Check status of a running tournament
./run.sh status table-merge-classifier

# Generate report from completed tournament
./run.sh report table-merge-classifier

# List all tournament histories
./run.sh list
```

## Manifest Schema

Tournaments are defined by YAML manifests:

```yaml
name: table-merge-classifier
description: "Classify whether adjacent PDF tables should merge"

scoring:
  metric_path: "$.selected_metrics.macro_f1"   # jsonpath into strategy JSON output
  gate_threshold: 0.90                          # target metric value
  direction: higher_better                      # higher_better | lower_better

convergence:
  max_rounds: 5
  plateau_window: 3        # consecutive rounds to detect plateau
  plateau_epsilon: 0.02    # max delta within plateau window

strategies:
  - name: tabular-gbr-features
    model: sonnet
    timeout_s: 600
    prompt: |
      Train a GBR classifier on {{ data_dir }} with normalized features.
      Use /classifier-lab benchmark --modality tabular --backbones gradient_boosting
      Output JSON with selected_metrics.macro_f1 field.

  - name: paired-siamese
    model: sonnet
    timeout_s: 1200
    prompt: |
      Train a Siamese EfficientNet on {{ data_dir }}/merge_images.
      Use /classifier-lab benchmark --modality paired --backbones efficientnet_b0
      Output JSON with selected_metrics.macro_f1 field.

  - name: tabular-ensemble
    model: sonnet
    timeout_s: 600
    prompt: |
      Train soft-voting ensemble (GBR+RF+LR) on {{ data_dir }}.
      Use /classifier-lab benchmark --modality tabular --backbones gradient_boosting,random_forest,logistic_regression
      Output JSON with selected_metrics.macro_f1 field.

reviewers:
  - name: brandon-bailey
  - name: tim-blazytko

variables:
  data_dir: /mnt/storage12tb/media/agents/shared/classifier-lab/data/table-merge

dogpile_on_failure: true
memory_scope: classifier-lab
```

## Manifest Fields

### Top-Level

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | str | Yes | Tournament name (used for /memory tracking) |
| `description` | str | No | Human-readable description |
| `scoring` | dict | Yes | How to extract and gate metrics |
| `convergence` | dict | Yes | When to stop iterating |
| `strategies` | list | Yes | Competing approaches (min 2) |
| `reviewers` | list | No | Persona agents for failure diagnosis |
| `variables` | dict | No | Template variables for strategy prompts |
| `dogpile_on_failure` | bool | No | Auto-/dogpile on plateau or combined failure |
| `memory_scope` | str | No | Scope for /memory tracking (default: tournament name) |

### Strategy

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | str | Yes | Strategy identifier |
| `model` | str | No | LLM model for /subagent-service (default: sonnet) |
| `prompt` | str | Yes* | Jinja2 template rendered with variables + round state |
| `skill` | str | No* | Alternative: call a /skill directly instead of prompt |
| `timeout_s` | int | No | Per-strategy timeout (default: 600) |

*One of `prompt` or `skill` is required.

### Scoring

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `metric_path` | str | Yes | JSONPath to extract metric from strategy output |
| `metric_regex` | str | No | Fallback regex to extract metric from text |
| `gate_threshold` | float | Yes | Target metric value |
| `direction` | str | No | `higher_better` (default) or `lower_better` |

### Convergence

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `max_rounds` | int | Yes | Maximum tournament rounds |
| `plateau_window` | int | No | Consecutive rounds for plateau detection (default: 3) |
| `plateau_epsilon` | float | No | Max delta within plateau window (default: 0.02) |

### Reviewer

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | str | Yes | Persona name (resolves to `.pi/agents/{name}/AGENTS.md`) |

## Template Variables

Strategy prompts are Jinja2 templates. Available variables:

| Variable | Description |
|----------|-------------|
| `{{ round }}` | Current round number |
| `{{ best_score }}` | Best metric score so far |
| `{{ best_strategy }}` | Name of best-performing strategy |
| `{{ prior_rounds }}` | JSON array of prior round results |
| `{{ diagnosis }}` | Diagnosis from previous round failure |
| `{{ dogpile_insights }}` | Research from /dogpile (if triggered) |
| Any key from `variables:` | User-defined variables from manifest |

## How It Works

```
FOR round in [1..max_rounds]:
  1. Render strategy prompts with current state
  2. Dispatch N strategies concurrently via /subagent-service
  3. Extract metric from each strategy's JSON output
  4. Score and rank strategies
  5. CHECK convergence gates:
     - Score >= threshold? → CONVERGED (stop)
     - Plateau detected?  → DIAGNOSE + /dogpile
     - Regression 2+ rounds? → DIAGNOSE + /dogpile
     - Round >= max? → EXHAUSTED (stop)
  6. On failure: persona reviewers diagnose, /dogpile researches
  7. Feed diagnosis + insights into next round's prompts
  8. Track everything to /memory
```

## /memory Tracking

Every round and every /dogpile call is stored in ArangoDB:

- **Rounds**: `THUNDERDOME:{name}:round{N}` with strategy scores, winner, diagnosis
- **Dogpile**: `DOGPILE:{name}:round{N}:{phase}` with query, result, context
- **Local backup**: `.artifacts/` JSON files per round

## Integration with Existing Labs

`/thunderdome` replaces the duplicated convergence loops in:

| Lab | Before | After |
|-----|--------|-------|
| `/classifier-lab` | Serial 10-step escalation in e2e_pipeline.py | Manifest with N concurrent strategies |
| `/prompt-lab` | Single-pass optimizer (no loop) | Manifest with prompt variants + eval scoring |
| `/paper-lab` | Planned but unimplemented | Manifest with revision strategies + reviewer personas |
| `/conversation-lab` | Custom convergence in conversation_lab.py | Manifest with scenario strategies + satisfaction scoring |
| `/music-lab` | Custom convergence in converge.py | Manifest with generation strategies + MIR scoring |
| `/figure-lab` | Custom iteration in figure_lab.py | Manifest with viz strategies + render scoring |

Each lab writes a manifest YAML and calls `/thunderdome run manifest.yaml`.
Domain-specific logic lives in the **strategy prompts**, not in orchestration code.

## Commands

| Command | Description |
|---------|-------------|
| `run` | Execute tournament from manifest |
| `status` | Show current round, best score, strategies tried |
| `report` | Generate markdown report from completed tournament |
| `list` | List all tournament histories in .artifacts/ |
