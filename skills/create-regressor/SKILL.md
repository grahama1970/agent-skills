---
name: create-regressor
description: >
  Train task-specific regression models from tabular data.
  Supports linear, ridge, lasso, gradient boosting, random forest, and XGBoost.
  Auto-selects best model via cross-validation. JSONL/CSV input, joblib output.
allowed-tools: Bash, Read, Write
triggers:
  - train regressor
  - create regressor
  - regression model
  - predict value
  - train regression
  - fit model
  - linear regression
  - gradient boosting regression
metadata:
  short-description: Train sklearn regression models from JSONL/CSV with auto model selection

provides:
  - create-regressor
  - regression-training
  - tabular-prediction
  - hp-tuning
composes:
  - dogpile        # Research best model approach when uncertain
  - memory         # Recall prior runs, learn results
  - analytics      # EDA before training
  - learn-timeout  # Domain consumer (timeout prediction uses create-regressor)
  - task-monitor
  - agentic-evals
taxonomy:
  - precision
  - resilience
  - regression
  - machine-learning
  - hyperparameter-tuning
  - self-improvement
disciplines:
  - ml-training
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Create Regressor

Train task-specific regression models (continuous target prediction) from tabular data. Parallel to `/create-classifier` (categorical targets) in the model training family.

## Model Training Family

| Skill | Target Type | Models | Input |
|-------|-------------|--------|-------|
| `/create-classifier` | Categorical (class labels) | EfficientNet, BERT, RF | Images, text |
| **`/create-regressor`** | **Continuous (numbers)** | **Linear, GBR, RF, XGB** | **Tabular JSONL/CSV** |
| `/create-gpt` | Language (text generation) | QLoRA on 0.5B-1.7B | Prompt/completion pairs |

## Minimum Training Data

For sklearn regressors, aim for at least 100 samples (10x the number of features).
Gradient boosting and random forest need more — at least 200+ samples to avoid
overfitting. With fewer than 100 samples, results will be unreliable regardless
of cross-validation scores.

## Quick Start

```bash
cd .pi/skills/create-regressor

# 1. Train from JSONL (auto-selects best model)
./run.sh train data.jsonl --target duration_seconds --name pdf-duration

# 2. Train specific model
./run.sh train data.csv --target price --model ridge --name house-price

# 3. Predict
./run.sh predict pdf-duration '{"page_count": 92, "tables": 15}'

# 4. Evaluate on held-out data
./run.sh evaluate pdf-duration --test test_data.jsonl

# 5. List all trained models
./run.sh status

# 6. Feature importance
./run.sh importance pdf-duration

# 7. Feed back actual values (online learning)
./run.sh observe pdf-duration --input '{"page_count": 92}' --actual 4200
```

## Supported Models

| Model | Key | Use When | Interpretable? |
|-------|-----|----------|----------------|
| Linear Regression | `linear` | Baseline, few features, interpretability | Yes |
| Ridge Regression | `ridge` | Multicollinearity, regularization needed | Yes |
| Lasso Regression | `lasso` | Feature selection, sparse models | Yes |
| ElasticNet | `elasticnet` | Mix of L1+L2 regularization | Yes |
| Gradient Boosting | `gbr` | Best accuracy, non-linear relationships | Partial |
| Random Forest | `rf` | Robust, handles outliers, no tuning needed | Partial |
| XGBoost | `xgb` | Large datasets, best competition accuracy | Partial |
| Auto (default) | `auto` | Cross-validates all, picks best by MAE | Varies |

## Commands

```bash
# Training
./run.sh train INPUT --target COL --name NAME [--model MODEL] [--test-split 0.2]
./run.sh train INPUT --target COL --name NAME --model auto  # CV-selects best

# Prediction
./run.sh predict NAME '{"feature": value, ...}'
./run.sh predict NAME --input batch.jsonl --output predictions.jsonl

# Evaluation
./run.sh evaluate NAME --test test.jsonl
./run.sh evaluate NAME --cv 5  # 5-fold cross-validation on training data

# Inspection
./run.sh status                      # List all trained models with metrics
./run.sh importance NAME             # Feature importance (sorted)
./run.sh residuals NAME --test test.jsonl  # Residual analysis

# Online feedback
./run.sh observe NAME --input '{"feat": val}' --actual 42.0

# Data utilities
./run.sh describe INPUT              # Schema discovery, stats, distributions
./run.sh split INPUT --test-ratio 0.2 --output-dir splits/
```

## Input Format

### JSONL (one JSON object per line)
```jsonl
{"page_count": 92, "tables": 15, "domain": "defense", "duration_seconds": 4200}
{"page_count": 12, "tables": 0, "domain": "arxiv", "duration_seconds": 180}
```

### CSV (header row + data)
```csv
page_count,tables,domain,duration_seconds
92,15,defense,4200
12,0,arxiv,180
```

## Output

### Training Output
```json
{
  "model_name": "pdf-duration",
  "model_type": "gradient_boosting",
  "selected_by": "auto_cv",
  "metrics": {
    "mae": 11.2,
    "rmse": 18.7,
    "r2": 0.984,
    "mape": 0.082
  },
  "cv_results": {
    "linear": {"mae": 45.2, "r2": 0.871},
    "ridge": {"mae": 44.8, "r2": 0.873},
    "gbr": {"mae": 11.2, "r2": 0.984},
    "rf": {"mae": 14.1, "r2": 0.976}
  },
  "training_samples": 446,
  "features": 33,
  "version": "2026-02-17_v1",
  "model_path": "models/pdf-duration/"
}
```

### Prediction Output
```json
{
  "prediction": 4200.5,
  "confidence_interval": [3100.0, 5300.0],
  "features_used": ["page_count", "tables", "domain"],
  "model_name": "pdf-duration",
  "model_type": "gradient_boosting"
}
```

## Feature Handling

- **Numeric**: Used directly (page_count, file_size_mb)
- **Categorical**: Auto one-hot encoded via DictVectorizer (domain, source)
- **Boolean**: Converted to 0/1 (has_tables, has_figures)
- **Missing**: Filled with 0 for numeric, "unknown" for categorical
- **Interaction**: Optionally generated via `--interactions` flag

## Model Registry

Each trained model is stored at `models/<name>/`:
```
models/pdf-duration/
  model.joblib           # Trained sklearn model + vectorizer
  training_summary.json  # Metrics, features, version
  feature_importance.json  # Feature name -> importance
  config.json            # Training config (model type, hyperparams)
  observations.jsonl     # Online feedback data
```

## Memory Integration

After training, model summary is stored in `/memory` for cross-skill recall:
- Tags: `[create-regressor, <model_name>, learned-model, Precision]`
- Problem: "Regression model: <name> — <description>"
- Solution: "Model type=<type>, MAE=<mae>, R2=<r2>, features=<n>, version=<v>"

## Relationship to /learn-timeout

`/learn-timeout` is a domain-specific consumer that could be refactored to use `/create-regressor`:
```bash
# Current (learn-timeout has its own GradientBoosting code):
cd .pi/skills/learn-timeout && ./run.sh train

# Future (learn-timeout calls create-regressor):
cd .pi/skills/create-regressor
./run.sh train /path/to/timeout/training_data.jsonl \
  --target actual_duration_s --name timeout-duration --model gbr
```

## Environment

```bash
# Optional: XGBoost (not in default deps)
pip install xgboost

# Models stored on 12TB drive via symlink
# data -> /mnt/storage12tb/media/agents/shared/create-regressor/data
# models -> /mnt/storage12tb/media/agents/shared/create-regressor/models
```
