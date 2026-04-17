---
name: regressor-lab
triggers:
  - regressor lab
  - regression benchmark
  - compare regressors
  - regressor shootout
description: >-
  Iterative regression model development lab. Benchmark multiple architectures
  (Linear, Ridge, GBR, RF, XGBoost, small GPT) against the same dataset,
  compare on holdout, tune hyperparameters, and feed results into Shadow-LEGO
  self-improvement loop.
provides: model-development
composes:
  - create-regressor
  - create-gpt
  - memory
  - assistant-lab
  - create-figure
  - task-monitor
taxonomy:
  - ml-ops
  - regression
  - benchmarking
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Regressor Lab

Iterative regression model benchmarking and development. Trains multiple
model architectures against the same dataset, compares on holdout, tunes
the winner, and optionally trains a small GPT for prediction rationale.

## Quick Start

```bash
# Benchmark all architectures on a dataset
./run.sh benchmark data.jsonl --target duration_ms --name timeout-estimator

# Benchmark with specific models
./run.sh benchmark data.jsonl --target duration_ms --models "gbr,xgb,rf,ridge"

# Tune the winner's hyperparameters
./run.sh tune timeout-estimator --trials 50

# Train a rationale GPT for the winner
./run.sh rationale timeout-estimator --train-gpt

# Evaluate on held-out test set
./run.sh evaluate timeout-estimator --test holdout.jsonl

# Compare two trained models head-to-head
./run.sh compare model-a model-b --test holdout.jsonl

# Full pipeline: benchmark → tune → rationale → deploy
./run.sh pipeline data.jsonl --target duration_ms --name timeout-estimator
```

## Architecture

```
regressor-lab
├── benchmark     Multi-architecture comparison (wraps /create-regressor)
├── tune          Hyperparameter search on best model
├── rationale     Train /create-gpt for prediction explanations
├── evaluate      Holdout evaluation with confidence intervals
├── compare       Head-to-head model comparison
├── pipeline      End-to-end: benchmark → tune → rationale → deploy
├── collect       Gather training data from extraction profiles
└── deploy        Wire winning model into target system
```

## Supported Architectures

| Model | Speed | Accuracy | When to use |
|-------|-------|----------|-------------|
| Linear | Ultra-fast | Baseline | Feature importance, interpretability |
| Ridge | Ultra-fast | Good | Multicollinear features |
| Lasso | Ultra-fast | Good | Feature selection |
| ElasticNet | Ultra-fast | Good | Mix of L1+L2 |
| GBR | Medium | Best | Non-linear, <100K rows |
| RF | Medium | Very good | Outlier-robust, parallel |
| XGBoost | Medium | Best | Large datasets, competition |
| GPT-rationale | Slow | N/A | Human-readable explanations |

## Data Format

JSONL with numeric, categorical, and boolean features:

```jsonl
{"page_count": 12, "file_size_mb": 1.35, "format": "pdf", "has_tables": true, "duration_ms": 3082}
{"page_count": 1, "file_size_mb": 0.004, "format": "html", "has_tables": false, "duration_ms": 25}
```

## Output Contract

Benchmark results are saved to `models/<name>/benchmark_results.json`:

```json
{
  "name": "timeout-estimator",
  "dataset_size": 15308,
  "train_size": 12246,
  "test_size": 3062,
  "target": "duration_ms",
  "results": [
    {"model": "xgb", "mae": 1234.5, "rmse": 2345.6, "r2": 0.92, "mape": 15.3, "train_seconds": 4.2},
    {"model": "gbr", "mae": 1345.6, "rmse": 2456.7, "r2": 0.91, "mape": 16.1, "train_seconds": 3.8},
    {"model": "rf",  "mae": 1456.7, "rmse": 2567.8, "r2": 0.89, "mape": 17.2, "train_seconds": 2.1}
  ],
  "winner": "xgb",
  "winner_metrics": {"mae": 1234.5, "rmse": 2345.6, "r2": 0.92},
  "tuned": false,
  "rationale_gpt": null
}
```

## Environment Variables

- `REGRESSOR_LAB_MODELS_DIR` — Override model storage (default: `./models`)
- `REGRESSOR_LAB_DATA_DIR` — Override data storage (default: `./data`)
