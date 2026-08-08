---
name: classifier-lab
triggers:
  - classifier-lab
  - train classifier
  - vision classifier
  - image classification
  - fine-tune vision model
  - text classifier
  - tabular classifier
  - text classification
  - flash classifier training
  - train classifier on flash
  - remote classifier training
description: Multi-modality classifier training lab. Train, evaluate, and deploy vision, text, and tabular classifiers using state-of-the-art backbones.
provides:
  - skill-creation
composes:
  - scillm
  - switchboard
  - memory
  - dogpile
  - create-figure
  - task-monitor
  - agentic-evals
taxonomy:
  - creation
  - training
  - classification
disciplines:
  - ml-training
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Classifier Lab

A multi-modality skill for training classifiers on custom datasets. Supports vision (image), text (transformer), and tabular (sklearn) classification.

## Minimum Training Data (NON-NEGOTIABLE)

**Do NOT benchmark a classifier trained on fewer than 200 samples per class.**

The rule is `n_samples / n_classes >= 200`. Models below this threshold will not
cross the 90% promotion gate. You're benchmarking noise, not a trained model.

If you have fewer than 200 samples per class, collect more labels via shadow mode
before training. See `/create-classifier` SKILL.md for evidence and thresholds.

## Quick Start

```bash
# Vision: Train a classifier (local, default)
./run.sh train --data-dir /path/to/images --backbone efficientnet_b0 --epochs 10

# Vision: Train on RunPod Flash (large backbones, 7B+ vision transformers)
./run.sh train --data-dir /path/to/images --backbone efficientnet_b0 --target flash --gpu B200

# Vision: Compare backbones
./run.sh benchmark --data-dir /path/to/images --backbones "efficientnet_b0,convnextv2_nano,fastvit_sa12"

# Text: Compare text backbones
./run.sh text-benchmark --labels-jsonl data/text.jsonl --backbones "prajjwal1/bert-tiny,distilbert-base-uncased"

# Tabular: Compare sklearn models
./run.sh tabular-benchmark --labels-jsonl data/features.jsonl --backbones "gradient_boosting,random_forest,logistic_regression"

# Explicit modality flag (equivalent to above shortcuts)
./run.sh benchmark --modality text --labels-jsonl data/text.jsonl --backbones "prajjwal1/bert-tiny"

# Evaluate a model
./run.sh evaluate --model models/my-classifier --data-dir /path/to/test

# Export for inference
./run.sh export --model models/my-classifier --format onnx
```

## Concurrent Training via Switchboard

Race multiple backbones simultaneously through Switchboard's deterministic executor.
Each backbone runs its own self-improvement loop with `/scillm` HP suggestions.

```bash
# Race 3 text classifiers concurrently
./run.sh concurrent-run \
    --task "intent classification" \
    --data-dir data/intents.jsonl \
    --modality text \
    --backbones "bert-base-uncased,distilbert-base-uncased,sentence-transformers/all-MiniLM-L6-v2" \
    --gate-f1 0.90 \
    --max-rounds 5

# Generate manifests only (inspect before submitting)
./run.sh concurrent-manifests \
    --task "table merge" \
    --data-dir /path/to/images \
    --modality vision
```

### How It Works

1. **Shared research**: `/dogpile` runs ONCE for the task (not per backbone)
2. **Shared data validation**: Data audit runs ONCE
3. **Per-backbone manifests**: Each backbone gets a Switchboard manifest with:
   - `train-loop` step: `backbone_train_loop.py` with self-improvement loop
   - `verify-gate` step: `check_metrics` on `metrics.json`
4. **Concurrent execution**: All manifests submitted to Switchboard, run in parallel
5. **Live leaderboard**: Poll loop reads progress files, broadcasts `TrainingRow[]` to UX
6. **Winner selection**: Best F1 across all backbones, stored to `/memory`

### Self-Improvement Loop (per backbone)

Each round: train → evaluate → gate check → `/scillm` HP suggestion → apply → retrain.

`/scillm` receives the **full training history** (all rounds, settings, results) as context
and returns structured JSON: `{learning_rate, batch_size, epochs, dropout, weight_decay, reasoning}`.
Code applies directly — no agent interpretation needed.

### Design Pattern

This is the standard pattern for all `*-lab` skills that need concurrent tasks.
Not all `/plan` tasks need Switchboard — only labs with multiple candidates racing.

| Approach | Use Case |
|----------|----------|
| `e2e` (sequential) | Single backbone, full 10-step escalation |
| `concurrent-run` (Switchboard) | Multiple backbones racing to a gate |

## Training Target: local vs flash

The `--target` flag selects where training runs:

| Target | Hardware | VRAM | Use Case | Cost |
|--------|----------|------|----------|------|
| `local` (default) | RTX A5000 | 24 GB | Standard backbones (EfficientNet, DistilBERT) | Free |
| `flash` | RunPod B200 / H200 | 192 GB | Large vision transformers, big text models | Pay-per-second |

**Flash** uses the RunPod serverless Python SDK — no Docker, no SSH.

> **Note**: Flash replaces `/ops-runpod` for all training paths.
> `/ops-runpod` is retained for persistent inference servers only.

### GPU types on Flash

| GPU | VRAM | Notes |
|-----|------|-------|
| `B200` | 192 GB HBM3e | Fastest; 3–5× H200 on large model training |
| `H200` | 192 GB HBM3 | Good availability; solid for most workloads |

Billing: pay-per-second, 7-day execution maximum per job.

### Flash cost estimates (approximate)

| Modality | Backbone | GPU | Est. Time | Est. Cost |
|----------|----------|-----|-----------|-----------|
| Vision (large ViT) | `vit_large_patch16_224` | B200 | ~30–60 min | ~$2–8 |
| Text (BERT-base) | `bert-base-uncased` | B200 | ~20–40 min | ~$1–5 |
| Text (large) | `roberta-large` | H200 | ~40–80 min | ~$3–10 |

> Always run a local benchmark with a small backbone first to validate data quality before escalating to Flash.

### Flash examples

```bash
# Train vision classifier on RunPod B200
./run.sh train --data-dir /path/to/images --backbone vit_large_patch16_224 --target flash --gpu B200

# Benchmark multiple text backbones on Flash
./run.sh text-benchmark --labels-jsonl data/text.jsonl \
  --backbones "bert-base-uncased,roberta-large" \
  --target flash --gpu H200

# Estimate cost before committing
./run.sh estimate --task my-classifier --target flash --gpu B200

# Tabular benchmark on Flash (uncommon — mostly useful for very large feature sets)
./run.sh tabular-benchmark --labels-jsonl data/features.jsonl \
  --backbones "gradient_boosting,random_forest" \
  --target flash --gpu B200
```

## Supported Backbones

### Vision

#### Tier 1: Best for Small Datasets
- `convnextv2_nano.fcmae_ft_in22k_in1k` - ConvNeXt V2 with FCMAE pre-training
- `convnextv2_tiny.fcmae_ft_in22k_in1k` - Larger variant
- `efficientnet_b0` - Strong baseline

#### Tier 2: Speed-Optimized
- `fastvit_sa12.apple_in1k` - Apple's fast hybrid
- `mobilenetv3_large_100` - Mobile-optimized
- `edgenext_small` - Edge deployment

#### Tier 3: Document-Specific
- `microsoft/dit-base` - Pre-trained on 42M documents
- `microsoft/layoutlmv3-base` - Text+image understanding

### Text

#### Tier 1: Ultra-Low Latency (<3ms)
- `prajjwal1/bert-tiny` - ~1.5ms, minimal footprint
- `sentence-transformers/all-MiniLM-L6-v2` - ~2.5ms, good accuracy

#### Tier 2: Balanced
- `microsoft/MiniLM-L12-H384-uncased` - ~3.5ms
- `distilbert-base-uncased` - ~5ms, reliable baseline

#### Tier 3: Maximum Accuracy
- `bert-base-uncased` - ~12ms, highest accuracy baseline

### Tabular

- `gradient_boosting` - GradientBoostingClassifier (sklearn)
- `random_forest` - RandomForestClassifier (sklearn)
- `logistic_regression` - LogisticRegression (sklearn)

## Data Formats

### Vision: Class Subdirectories
```
data/
├── train/
│   ├── class_a/
│   │   ├── image1.png
│   │   └── image2.png
│   └── class_b/
│       └── image3.png
└── val/
    ├── class_a/
    └── class_b/
```

### Vision: JSONL
```json
{"image_path": "path/to/image.png", "label": "class_a", "metadata": {...}}
```

### Text: JSONL
```json
{"text": "The satellite lost telemetry.", "label": "anomaly"}
{"text": "Normal operations resumed.", "label": "nominal"}
```

Multilabel variant:
```json
{"text": "GPS jamming detected on L1 band.", "labels": ["jamming", "gps"]}
```

### Tabular: JSONL
```json
{"features": {"temperature": 23.5, "pressure": 101.3, "vibration": 0.02}, "label": "nominal"}
{"features": {"temperature": 89.1, "pressure": 45.2, "vibration": 3.71}, "label": "fault"}
```

## Features

- **Multi-Modality**: Vision, text, and tabular in one skill
- **Backbone A/B Testing**: Compare multiple backbones on your data
- **Latency Profiling**: Text benchmarks include p50/p95 inference latency
- **Hyperparameter Tuning**: Grid search or Optuna integration
- **Ensemble Support**: Combine predictions from multiple models
- **Data Augmentation**: RandAugment, MixUp, CutMix (vision)
- **Export Formats**: PyTorch, ONNX, TorchScript
- **Metrics**: Accuracy, F1, Wilson score lower bound (99% CI), confusion matrix, per-class metrics
- **Federated Taxonomy**: Benchmark summaries are tagged for cross-collection graph traversal
- **Memory Integration**: Benchmark events are persisted to memory for longitudinal learning

## Output Contract (Benchmark)

All modalities produce identical top-level JSON:

```json
{
  "status": "ok|failed",
  "selected_backbone": "model_name",
  "selected_metrics": {"macro_f1": 0.95, "accuracy": 0.93, "wilson_score_lower": 0.91},
  "source": {"mode": "jsonl|data_dir", "...": "..."},
  "results": [{"backbone": "...", "status": "ok", "macro_f1": 0.95, "...": "..."}],
  "taxonomy": {"status": "ok", "result": {"...": "..."}},
  "memory_store": {"status": "ok", "...": "..."}
}
```

Text modality adds latency to `selected_metrics`:
```json
{
  "selected_metrics": {
    "macro_f1": 0.95, "accuracy": 0.93,
    "latency_p50_ms": 2.5, "latency_p95_ms": 4.1
  }
}
```

For strict quality pipelines:

- keep `--store-memory` and `--require-memory-store` enabled
- treat benchmark run as failed when memory write is not successful

## Mandatory Training Monitoring (NON-NEGOTIABLE)

**You MUST monitor training runs. Never fire-and-forget.**

### During Training

After launching a benchmark with `./run.sh benchmark` or `./run.sh text-benchmark`:

1. **Check status every 2-5 minutes** while training runs:
   ```bash
   ./run.sh status          # Shows running/completed benchmarks
   ./run.sh status --json   # Machine-readable for agent parsing
   ```

2. **Check TensorBoard data** when available:
   ```bash
   ./run.sh tb-summary          # Human-readable loss/convergence
   ./run.sh tb-summary --json   # Machine-readable for agent parsing
   ```

3. **Assess convergence**: If `tb-summary` reports `diverging` or loss is increasing, STOP and investigate:
   - Learning rate too high? Try 1e-5 instead of 2e-5
   - Data quality issue? Check label distribution
   - Wrong loss function? Multi-label needs BCEWithLogitsLoss, not CrossEntropy

### After Training Completes

4. **Read the output JSON** and verify metrics meet targets:
   ```bash
   cat /tmp/<output>.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'F1={d[\"macro_f1\"]:.3f} acc={d[\"accuracy\"]:.3f} wilson={d[\"wilson_lb\"]:.3f}')"
   ```

5. **Course-correct if metrics are below target**:
   - macro_f1 < 0.85 → investigate per-class breakdown, add more training data
   - accuracy < 0.80 → likely data quality issue or wrong backbone
   - wilson_lb < 0.75 → insufficient validation samples

6. **Never declare "done" without reporting metrics** to the user.

### Anti-Patterns (DO NOT)

- Launch training and pipe to `tail -30` without monitoring
- Declare training "started" and move on without checking results
- Skip TB monitoring because tensorboard "isn't installed" (it IS installed)
- Report on code changes without reporting evaluation metrics

See [SELF_IMPROVEMENT.md](references/SELF_IMPROVEMENT.md) for the full self-improvement loop, strategy escalation, data sufficiency checks, and research gate details.

---

## Common Mistakes

### WRONG: Training without running /dogpile research and local data audit first
```bash
./run.sh benchmark --data-dir /path/to/images --backbones "efficientnet_b0"
# No data_audit.json, no research.md — training is blocked
```

### RIGHT: Audit data locally, then dogpile, then train
```bash
# 1. Create data_audit.json with class balance, feature quality, resolution
# 2. Run /dogpile informed by audit findings
# 3. Then train
./run.sh benchmark --data-dir /path/to/images --backbones "efficientnet_b0"
```

### WRONG: Reporting validation metrics as evaluation results
```python
print(f"F1={val_f1:.3f}")  # This is val set, not held-out test set!
```

### RIGHT: Always evaluate on held-out test set
```bash
./run.sh evaluate --model models/my-classifier --data-dir /path/to/test
# Report test F1, not validation F1
```

### WRONG: Training with fewer than 200 samples per class
```bash
./run.sh benchmark --data-dir data/ --backbones "efficientnet_b0"
# 50 samples, 5 classes = 10/class — will not cross 90% gate
```

### RIGHT: Verify minimum data before training
```
n_samples / n_classes >= 200  # hard minimum for promotion
```
