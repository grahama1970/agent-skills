---
name: assistant-lab
description: >
  Self-improvement workbench for /assistant. All the tools needed to
  diagnose, train, evaluate, and promote models in a continuous loop.
  The "warm pond" where /assistant evolves its own inference stack.
triggers:
  - assistant lab
  - assistant-lab
  - improve assistant
  - train assistant model
  - assistant self-improve
  - warm pond
  - model factory
  - auto improve
  - train remote
  - train on runpod
  - remote training
  - train larger model
  - runpod training cost
  - train on flash
  - flash training
  - runpod flash training
  - flash assistant training
allowed-tools:
  - Bash
  - Python
metadata:
  short-description: Self-improvement workbench for /assistant
env:
  - ASSISTANT_MODELS_DIR (default: ~/.pi/models)
  - ASSISTANT_METRICS_DIR (default: ~/.pi/assistant)

provides:
  - assistant-self-improvement
  - remote-training-orchestration
composes:
  - create-gpt
  - create-classifier
  - create-regressor
  - gpt-lab
  - classifier-lab
  - prompt-lab
  - assistant
  - scillm
  - ops-runpod
  - task-monitor
  - agentic-evals
disciplines:
  - ml-training
  - evaluation-quality
---

# assistant-lab

Self-improvement workbench for `/assistant`. This is the **lab** where
/assistant diagnoses problems, trains new models, evaluates them, and
promotes passing models into the live registry.

**Not to be confused with `/monitor-skills`** which is the observability
daemon that watches ALL skills for health, drift, and sync issues.
`/assistant-lab` is specifically the self-improvement toolbox.

## The Self-Improvement Loop

```
/monitor-skills detects problem    ← observability
    ↓
/assistant-lab diagnoses root cause ← this skill
    ↓
Shadow mode: teacher (scillm) labels flow into shadow.jsonl
    ↓
ModelFactory.auto_improve(task)
    ├─ reads shadow agreement rate
    ├─ >= 90%: promote → update model_registry.json
    ├─ 80-90%: plateau → /prompt-lab redesign
    ├─ 70-80%: retrain → /create-gpt or /create-classifier
    └─ < 70%: aggressive retrain + architecture change
    ↓
/gpt-lab benchmark or /classifier-lab evaluate
    ↓ passing? → promote to live registry
    ↓
/assistant uses the improved model at inference time
```

## Tools Available

| Tool | Purpose | When Used |
|------|---------|-----------|
| `/create-gpt` | Train QLoRA/SFT/GRPO GPT (Tier 1.5) | Agreement < 80% or no model exists |
| `/create-classifier` | Train DistilBERT/sklearn classifier (Tier 0.5) | Text classification tasks |
| `/create-regressor` | Train sklearn/XGB regressor (Tier 0.75) | Continuous prediction tasks |
| RunPod Flash | Serverless GPU training via Python SDK (7B–70B) | Model too large for local A5000 — replaces `/ops-runpod` for training |
| `/gpt-lab` | Benchmark GPT against teacher baseline | After training, before promotion |
| `/classifier-lab` | Evaluate classifier accuracy/F1 | After classifier training |
| `/prompt-lab` | Redesign prompts when plateau detected | Agreement stuck at 80-90% |
| `/scillm` | Tier 2 teacher — creates labels | Always (teacher is ground truth) |

## Usage

### CLI

```bash
# Diagnose what a task needs
./run.sh diagnose --task stress-test-grader

# Full autonomous improvement loop
./run.sh auto-improve --task stress-test-grader

# Train specific model type
./run.sh train --task stress-test-grader --type gpt
./run.sh train --task sparta-ambiguity --type classifier

# Evaluate a model
./run.sh evaluate --task stress-test-grader --type gpt

# Promote a passing model (disables shadow mode)
./run.sh promote --task stress-test-grader --type gpt

# Harvest teacher labels from shadow.jsonl
./run.sh harvest --task stress-test-grader --since 24h

# Show shadow agreement stats for all tasks
./run.sh status

# Run full self-test (train → eval → promote cycle on test data)
./run.sh self-test
```

### Python API

```python
from assistant_lab import AssistantLab

lab = AssistantLab()

# Diagnose: what does this task need?
diagnosis = lab.diagnose("stress-test-grader")
# → {"has_gpt": False, "has_classifier": False, "shadow_agreement": 0.0, ...}

# Auto-improve: decide + train + eval + promote
result = lab.auto_improve("stress-test-grader")
# → {"actions": ["trained gpt", "evaluated (passing=True)", "promoted"]}

# Manual steps
lab.train("stress-test-grader", model_type="gpt")
lab.evaluate("stress-test-grader", model_type="gpt")
lab.promote("stress-test-grader", model_type="gpt")
```

## Model Factory

The core engine is `ModelFactory` (from `/common/model_factory.py`).
`/assistant-lab` wraps it with CLI + diagnostics + reporting.

### Shadow Agreement Thresholds

| Agreement Rate | Action | Rationale |
|----------------|--------|-----------|
| >= 90% | **Promote** | Student reliably matches teacher |
| 80-90% | **/prompt-lab** redesign | Plateau — prompts may be the ceiling |
| 70-80% | **Retrain** with more labels | More data likely helps |
| < 70% | **Aggressive retrain** | Change architecture or base model |
| < 50 samples | **Wait** | Not enough data to decide |

### Minimum Training Data (NON-NEGOTIABLE)

**Do NOT call `/create-gpt train` or `/create-classifier train` with insufficient data.**

| Model Type | Minimum Samples | Rule |
|------------|----------------|------|
| GPT (QLoRA SFT) | 1,000+ total | < 1,000 → stays at Tier 2 teacher |
| Classifier (sklearn/SetFit) | 200 per class | `n_samples / n_classes >= 200` |
| Regressor | 100+ total | Standard sklearn guidance |

Evidence: `sparta_stress_grading` was trained on 246 samples → 33.7% agreement.
That's 4 months of wasted shadow labels because the model was trained too early.
**Collect first, train when ready.**

### Training Data Flow

```
Tier 2 teacher (scillm via persona)
    ↓ labels saved to shadow.jsonl
    ↓
/assistant-lab harvest --task X
    ↓ extracts input+output pairs
    ↓
/create-gpt train --task X --data labels.jsonl
    ↓ QLoRA on Qwen2.5-1.5B (default)
    ↓
/gpt-lab benchmark --task X
    ↓ compare student vs teacher
    ↓
/assistant-lab promote --task X --type gpt
    ↓ updates model_registry.json, shadow_mode=false
```

## Remote Training (RunPod Flash)

For models too large for the local RTX A5000 (24GB VRAM, max ~1.7B with LoRA),
`assistant-lab` uses **RunPod Flash** — the serverless Python SDK with no Docker,
no SSH, and no rsync overhead. Flash **replaces `/ops-runpod`** for all training
paths. `/ops-runpod` is retained for persistent inference servers only.

### When to Use Flash

| Model Size | Local A5000 | Flash Needed | GPU |
|-----------|-------------|--------------|-----|
| 0.5–1.7B | LoRA fits | No | `./run.sh train` (local) |
| 3–7B | Can't fit | **Yes** | B200 (preferred) or H200 |
| 8–13B | Impossible | **Yes** | B200 (preferred) or H200 |

### Flash GPU Types

| GPU | VRAM | Notes |
|-----|------|-------|
| `B200` | 192 GB HBM3e | Fastest; 3–5× H200 on MoE / long-context |
| `H200` | 192 GB HBM3 | Good availability; solid baseline |

Billing: pay-per-second, 7-day execution maximum per job.

### Flash cost estimates (approximate)

| Model Size | GPU | Est. Training Time | Est. Cost |
|------------|-----|--------------------|-----------|
| 7B QLoRA SFT | B200 | ~1–2 hrs | ~$5–15 |
| 7B QLoRA SFT | H200 | ~2–3 hrs | ~$8–20 |
| 13B QLoRA SFT | B200 | ~2–4 hrs | ~$10–25 |
| 13B QLoRA SFT | H200 | ~3–5 hrs | ~$12–30 |

### Commands

```bash
# Step 1: Always estimate cost first
./run.sh estimate --task taxonomy-assessor --target flash --gpu B200 --size 7B

# Step 2: Train on Flash B200 (requires --confirm for safety)
./run.sh train --task taxonomy-assessor --target flash --gpu B200 --size 7B --confirm

# Train on Flash H200
./run.sh train --task taxonomy-assessor --target flash --gpu H200 --size 13B --confirm

# With custom base model
./run.sh train --task taxonomy-assessor --target flash --gpu B200 --size 8B \
  --base-model meta-llama/Llama-3.1-8B-Instruct --confirm

# With different quantization
./run.sh train --task qra-validator --target flash --gpu B200 --size 7B \
  --quantize Q5_K_M --confirm
```

### Flash Training Pipeline

```
estimate --target flash --gpu B200 --size 7B
    ↓
train --target flash --gpu B200 --confirm
    ├─ 1. Cost estimate + budget gate
    ├─ 2. Flash serverless job submitted (Python SDK — no Docker/SSH)
    ├─ 3. Dataset streamed to Flash worker
    ├─ 4. QLoRA / SFT training runs on B200/H200 (192GB VRAM)
    ├─ 5. Pull model weights to /mnt/storage12tb/models/
    ├─ 6. create-gpt export --quantize Q4_K_M (GGUF)
    └─ 7. Evaluate + auto-promote if passing
```

### Safety Gates

- **Budget cap**: `--max-cost` (default $15.00) blocks training if estimate exceeds limit
- **Confirmation**: Must pass `--confirm` — without it, shows cost and exits
- **Auto-teardown**: Flash job is cancelled on exit (even on error, via trap)
- **Metrics logging**: Every Flash training run logged to `lab_metrics.jsonl`

### Integration with Self-Improvement Loop

Remote-trained models integrate with the same cascade as local models:

```
Tier 0:   Heuristic (free, instant)
Tier 0.5: Classifier (local, free)
Tier 1.5: Local GPT ≤1.7B (create-gpt, free after training)
Tier 1.5: Remote GPT 3-13B (train-remote, free after training)  ← NEW
Tier 2:   scillm/DeepSeek V3 (Chutes, $0.12/1K calls)
```

A 7-13B model at Tier 1.5 can significantly reduce Tier 2 (Chutes) escalations,
potentially paying for its training cost in reduced overages.

## Relationship to Other Skills

```
/monitor-skills ──→ "skill X is unhealthy"
                         ↓
/assistant-lab ──→ diagnose → train → eval → promote
                         ↓
/assistant ──────→ uses promoted model at inference time
```

- **`/monitor-skills`**: Observes ALL skills. Detects problems. Reports health.
- **`/assistant-lab`**: Fixes /assistant's models. Trains, evaluates, promotes.
- **`/assistant`**: Runs inference. Uses whatever models the lab has produced.

## Contract

- **Input**: Task name + optional model type
- **Output**: Diagnosis, training results, evaluation results, promotion status
- **Dependencies**: model_factory.py (from /common), create-* and *-lab skills
- **Metrics**: Appends to `~/.pi/assistant/lab_metrics.jsonl`
