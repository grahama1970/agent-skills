---
name: create-classifier
description: >
  Train task-specific classifiers for the extractor pipeline.
  Supports vision, text, and hybrid classifiers with GRPO training and execution feedback.
  Includes data collection, confidence-based routing, and shadow deployment.
allowed-tools: Bash, Read, Write
triggers:
  - train classifier
  - create classifier
  - classifier training
  - document type classifier
  - ml model training
metadata:
  short-description: Generalized classifier training infrastructure with execution feedback

provides:
  - create-classifier
composes:
  - memory
  - classifier-lab
  - dogpile
  - task-monitor
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Create Classifier Skill

> **Purpose**: Training infrastructure for task-specific classifiers that improve extractor pipeline accuracy through ML-based detection instead of regex/heuristics.

## Overview

This skill provides end-to-end infrastructure for creating, training, and deploying classifiers for extraction tasks:

- **Data Collection**: Mine labeled data from successful pipeline runs
- **Training Templates**: Vision, text, and hybrid classifier architectures
- **Execution Feedback**: GRPO-style training with pipeline success as reward
- **Confidence Routing**: Automatic fallback to heuristics when confidence is low
- **Shadow Deployment**: Compare classifier vs heuristics before full rollout

## Success Story: Table Strategy Classifier

The table extraction classifier (S05) achieved:

- **95.07% accuracy** (vs ~75% heuristic baseline)
- **Reduced fallback rate** from ~25% to <10%
- **Faster inference** than multi-strategy attempts

This skill generalizes that success pattern for other extraction tasks.

---

## Minimum Training Data (NON-NEGOTIABLE)

**Do NOT train a classifier with fewer than 200 samples per class.**

The simplest predictor of promotion success is `n_samples / n_classes >= 200`.

Evidence from the production model registry (16 classifiers):
- **All 10 classifiers above the 90% promotion gate** had >= 1,161 total samples
- **All 6 classifiers below the gate** had insufficient data for their task complexity:
  - sparta-intent: 50 samples, 12 classes → 44% (4 samples/class!)
  - 5ft-intent: 120 samples, 13 classes → 52.5% (9 samples/class)
  - qra-assessor: 53 samples, 3 classes → 85% (18 samples/class)
  - bridge-tagger: 3,734 samples, 6 multi-label classes → 63.8%

If you have fewer than 200 samples per class:
1. **Stay at Tier 2** (teacher via /scillm) and collect more shadow labels
2. Use `/assistant-lab harvest` to accumulate teacher labels over time
3. Do NOT train — the model will not cross the 90% promotion gate

## Supported Classifier Types

### 1. Vision Classifiers

**Use case**: Document-level classification from images

- **Example**: S00 document type detection (arxiv, requirements_spec, legal)
- **Input**: First 3 pages as images (224x224)
- **Architecture**: EfficientNet-B0 or DiT (Document Image Transformer)

### 2. Text Classifiers

**Use case**: Sentence or block-level classification from text

- **Example**: S08 requirement sentence detection
- **Input**: Sentence text + context (headings, modal verbs)
- **Architecture**: BERT-base or RoBERTa

### 3. Hybrid Classifiers

**Use case**: Combined text + layout features

- **Example**: S04 citation vs section header detection
- **Input**: Text + font size + bbox + surrounding context
- **Architecture**: Multi-modal fusion network

---

## Usage

### Step 0: Preflight Assess (Recommended)

Run an initial task/data assessment before training. This recommends classifier family/backbone,
checks class imbalance, and can trigger `/dogpile` research when confidence is low.

```bash
./run.sh assess \
  --task document_type \
  --labels data/labels/document_type.jsonl \
  --dogpile-when-uncertain
```

### Step 0b: Benchmark-First Model Selection (Recommended)

Run benchmark-first selection after assess. This attempts `classifier-lab` first
when configured, then uses internal quick benchmarking as deterministic fallback.
For production training, make classifier-lab mandatory and fail closed on selection.

```bash
./run.sh select-model \
  --labels data/labels/document_type.jsonl \
  --model efficientnet_b0 \
  --candidate-backbones \
    efficientnet_b0,convnextv2_nano.fcmae_ft_in22k_in1k,resnet50 \
  --benchmark-first \
  --classifier-lab-first \
  --require-classifier-lab \
  --require-selection-pass
```

### Step 1: Data Collection

Collect labeled examples from successful pipeline runs:

```bash
./run.sh collect \
  --task document_type \
  --source /path/to/corpus \
  --output data/labels/document_type.jsonl
```

**Output format** (JSONL):

```json
{
  "id": "doc_abc123",
  "task": "document_type",
  "input": {
    "image_paths": ["page_0.png", "page_1.png", "page_2.png"],
    "text_features": { "page_count": 42, "has_formulas": true }
  },
  "label": "arxiv_scientific",
  "confidence": 0.95,
  "source": "successful_extraction"
}
```

### Step 2: Train Classifier

Train using supervised learning or GRPO (with execution feedback):

````bash
# Supervised fine-tuning (SFT)
./run.sh train \
  --config configs/document_type.yaml \
  --mode sft \
  --epochs 20

# GRPO with execution feedback
./run.sh train \
  --config configs/document_type.yaml \
  --mode grpo \
  --feedback-fn validate_pipeline_success

# Iterative train with preflight assess, optional HF augmentation, and holdout gate
./run.sh train-iterative \
  --task document_type \
  --model efficientnet_b0 \
  --labels data/labels/document_type.jsonl \
  --output-dir models/document_type \
  --benchmark-first \
  --classifier-lab-first \
  --require-classifier-lab \
  --require-selection-pass \
  --run-preflight-assess \
  --auto-hf-augment \
  --run-hp-search

# Strict quality gate profile (recommended default)
# - holdout macro-F1 >= 0.90
# - holdout accuracy >= 0.90
# - per-class recall floor >= 0.80 (enforce in evaluator/report gate)

### Step 2b: Train with Docker

Run training in a container (recommended for reproducibility):

```bash
docker-compose up classifier
````

This mounts the corpus and output directories automatically.

````

### Step 3: Evaluate

Compare classifier against heuristic baseline:

```bash
./run.sh evaluate \
  --model models/document_type \
  --baseline heuristic \
  --test-set data/test/document_type.jsonl
````

**Success criteria**:

- Overall accuracy >90%
- Per-class precision >80%
- Inference time <100ms

### Step 4: Shadow Deploy

Run classifier in parallel with heuristics (log differences, no changes to pipeline):

```bash
./run.sh shadow-deploy \
  --model models/document_type \
  --target s00_profile_detector \
  --duration 7d \
  --log-path logs/shadow_deploy.jsonl
```

### Step 5: Deploy

If metrics pass, deploy to production:

```bash
./run.sh deploy \
  --model models/document_type \
  --target extractor \
  --confidence-threshold 0.8
```

---

## Configuration Files

### Document Type Classifier (`configs/document_type.yaml`)

```yaml
task: document_type
type: vision

classes:
  - arxiv_scientific
  - requirements_spec
  - legal_contract
  - general

model:
  architecture: efficientnet_b0
  pretrained: true
  input_size: 224
  num_pages: 3 # First 3 pages

training:
  epochs: 20
  batch_size: 16
  learning_rate: 0.001
  optimizer: adam

confidence:
  threshold: 0.8 # Route to heuristic if below

feedback:
  mode: grpo # or 'sft'
  reward_fn: validate_preset_accuracy
  baseline: heuristic
```

### Requirements Classifier (`configs/requirements.yaml`)

```yaml
task: requirement_detection
type: text

classes:
  - requirement
  - non_requirement

model:
  architecture: bert-base-uncased
  max_length: 256

training:
  epochs: 10
  batch_size: 32
  learning_rate: 2e-5

confidence:
  threshold: 0.9 # High precision needed
```

---

See [ARCHITECTURE.md](references/ARCHITECTURE.md) for architecture details, confidence routing, GRPO training, and integration examples.

---

            # Fallback to heuristic
            return {
                "prediction": self.heuristic(input_data),
                "source": "heuristic",
                "classifier_confidence": confidence  # Log anyway
            }
```

---

    # 47 regex patterns for section numbering
    # Formula detection regex
    # Font-size analysis
    # ~85% accuracy, confidence often <0.8
    return {"preset": "arxiv", "confidence": 0.7}
```

### After (Classifier + Fallback)

```python
def detect_preset(pdf_path):
    # Try classifier first
    result = preset_classifier.predict(pdf_path)

    if result["confidence"] >= 0.8:
        return result  # Use classifier
    else:
        # Fallback to heuristics
        return detect_preset_heuristic(pdf_path)
```

**Benefits**:

- Higher accuracy (90%+ vs 85%)
- Faster (single forward pass vs 47 regex patterns)
- Continuous improvement (retrain with production data)

---

## Files

```
create-classifier/
├── SKILL.md                    # This file
├── run.sh                      # CLI wrapper
├── .env.example               # Configuration template
├── scripts/
│   ├── collect_labels.py      # Mine labels from pipeline
│   ├── train_vision.py        # Vision classifier training
│   ├── train_text.py          # Text classifier training
│   ├── evaluate.py            # Evaluation & comparison
│   └── deploy.py              # Generate inference code
├── templates/
│   ├── vision_classifier.py   # EfficientNet/DiT template
│   ├── text_classifier.py     # BERT/RoBERTa template
│   └── hybrid_classifier.py   # Multi-modal template
├── configs/
│   ├── document_type.yaml     # S00 preset detection
│   ├── requirements.yaml      # S08 requirement detection
│   └── citation_filter.yaml   # S04 citation filtering
└── utils/
    ├── data_collection.py     # Dataset utilities
    ├── confidence_routing.py  # Routing logic
    └── shadow_deploy.py       # Parallel testing
```

---

## Dependencies

```toml
[tool.uv.dependencies]
torch = "^2.0.0"
timm = "^0.9.0"              # Vision models
transformers = "^4.30.0"     # Text models
trl = "^0.7.0"               # GRPO training
pillow = "^10.0.0"           # Image processing
pyyaml = "^6.0"
loguru = "^0.7.0"
```

---

## Common Mistakes

### WRONG: Training with fewer than 200 samples per class
```bash
./run.sh train --config configs/document_type.yaml --mode sft
# Only 50 samples for 5 classes — will not pass 90% gate
```

### RIGHT: Check data sufficiency before training
```bash
# Verify n_samples / n_classes >= 200
# If insufficient, stay at Tier 2 and harvest more shadow labels
./run.sh collect --task document_type --source /path/to/corpus --output data/labels/
```

### WRONG: Deploying without shadow comparison
```bash
./run.sh deploy --model models/document_type --target extractor  # no shadow data!
```

### RIGHT: Shadow deploy first, compare against heuristics, then deploy
```bash
./run.sh shadow-deploy --model models/document_type --target s00_profile_detector --duration 7d
# After 7d of comparison data, then deploy if metrics pass
./run.sh deploy --model models/document_type --target extractor --confidence-threshold 0.8
```

### WRONG: Skipping benchmark-first model selection
```bash
./run.sh train --config configs/document_type.yaml  # default backbone, never compared
```

### RIGHT: Benchmark multiple backbones, then train the winner
```bash
./run.sh select-model --labels data/labels/ --benchmark-first \
  --candidate-backbones efficientnet_b0,convnextv2_nano,resnet50
```
