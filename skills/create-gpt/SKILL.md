---
name: create-gpt
description: >
  Train task-specific small GPTs (0.5B-1.7B) for Tier 1.5 inference. Supports QLoRA SFT,
  GRPO with pluggable rewards, Karpathy microgpt from-scratch training, Optuna HP search,
  iterative self-improvement with holdout gates, and GGUF export for production inference.
allowed-tools: Bash, Read
triggers:
  - train small gpt
  - create gpt model
  - fine-tune small model
  - tier 1.5 training
  - qlora sft training
  - grpo task training
  - microgpt training
  - train validator
  - confidence routing
  - train on flash
  - flash training
  - remote flash training
  - train larger model flash
metadata:
  short-description: Train task-specific small GPTs for Tier 1.5 inference

provides:
  - create-gpt
composes:
  - memory
  - task-monitor
  - agentic-evals
disciplines:
  - ml-training
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Create GPT

Train task-specific small GPTs (0.5B-1.7B) that fill the Tier 1.5 gap in the inference cascade.
These are **specialists, not generalists** — they handle JSON validation, taxonomy triage,
and "needs_review" gating. Cases with low confidence escalate to Chutes via `/scillm`.

## Prompt Iteration Rule (NON-NEGOTIABLE)

System prompts in SFT training data MUST be validated through `/prompt-lab` before training. NEVER hand-craft system prompts in Python strings or JSONL files.

- Before training: `/prompt-lab eval` the system prompt against holdout ground truth
- Comparing prompt variants: `/prompt-lab compare` across models
- Finding minimum viable model: `/prompt-lab find-minimum`
- Only after prompt-lab validation → proceed to `/create-gpt train`

## Inference Cascade

| Tier | Method | Cost | Latency |
|------|--------|------|---------|
| 0 | Deterministic (regex, JSON schema) | Free | Microseconds |
| 1 | sklearn classifiers (RF on embeddings) | Free | Milliseconds |
| **1.5** | **Small GPT (this skill)** | **Free** | **~200ms** |
| 2 | `/scillm` Chutes DeepSeek V3.2-TEE | ~$0.12/1K | ~2-5s |

## Quick Start

```bash
cd .pi/skills/create-gpt

# 1. Define a task from YAML spec
./run.sh define --name qra-validator --from-yaml data/tasks/qra-validator.yaml

# 2. Prepare training data
./run.sh prepare --task qra-validator --input raw.jsonl

# 3. Train (mock mode for testing)
./run.sh train --task qra-validator --sft-only --mock

# 4. Evaluate
./run.sh evaluate --task qra-validator --mock

# 5. Export to GGUF for production
./run.sh export --task qra-validator --quantize Q4_K_M

# 6. Inference with confidence routing
./run.sh route '{"question": "test?"}' --task qra-validator --threshold 0.85
```

## Minimum Training Data (NON-NEGOTIABLE)

**Do NOT attempt QLoRA SFT with fewer than 1,000 training examples.**

Evidence from the production model registry (51 models):
- **sparta_stress_grading**: 246 samples → 33.7% shadow agreement (FAILURE)
- **page-anticipation**: 201 samples → 100% holdout BUT only 14 classes on a trivially separable task
- **sparta-rationale**: 8,000 samples → 94.5% token accuracy (SUCCESS)
- **proof-rationale**: 3,500 samples → 92.2% token accuracy (SUCCESS)

**Rule of thumb**: For structured JSON generation tasks, you need `>= 1,000` examples
for a 0.5B model and `>= 2,000` for a 1.5B model. For tasks with nuanced judgment
(grading, quality assessment), you need `>= 5,000`.

If you have fewer than 1,000 examples:
1. **Stay at Tier 2** (teacher via /scillm) and collect more shadow labels
2. Use `/assistant-lab harvest` to accumulate teacher labels over time
3. Do NOT train — you will waste GPU time and get a model that can't be promoted

## Training Approaches

| Approach | Use When | Model Size | Min Samples |
|----------|----------|------------|-------------|
| **SFT + GRPO** | Task needs language understanding, >1K examples | 0.5B-1.7B | 1,000+ |
| **SFT Only** | Quick baseline, simple tasks | 0.5B-1.7B | 1,000+ |
| **Karpathy microgpt** | Ultra-narrow task, <10K examples, need ~50us | <10M params | 500+ |
| **Iterative** | Production quality needed, automated convergence | 0.5B-1.7B | 2,000+ |

## Commands

```bash
# Task definition
./run.sh define --name NAME --from-yaml YAML_FILE

# Data preparation
./run.sh prepare --task NAME --input FILE [--augment] [--limit N]
./run.sh split --task NAME --holdout-ratio 0.10

# Training (local, default)
./run.sh train --task NAME [--sft-only] [--grpo-steps 2000] [--mock] [--wandb]
./run.sh train-micro --task NAME --data FILE [--layers 6] [--dim 128]

# Training (RunPod Flash — 7B+ models)
./run.sh train --task NAME --target flash --gpu B200 [--size 7B] [--sft-only]
./run.sh train --task NAME --target flash --gpu H200 [--size 13B] [--grpo-steps 2000]
./run.sh estimate --task NAME --target flash --gpu B200 --size 7B

# Self-improvement
./run.sh hp-search --task NAME [--trials 15] [--resume]
./run.sh iterate --task NAME [--max-iterations 5] [--quality-threshold 0.85]

# Evaluation & Export
./run.sh evaluate --task NAME [--holdout] [--mock]
./run.sh export --task NAME [--quantize Q4_K_M]

# Inference
./run.sh infer "input" --task NAME [--mode gguf|hf]
./run.sh route "input" --task NAME [--threshold 0.85]
```

## Training Target: local vs flash

The `--target` flag selects where training runs:

| Target | Hardware | VRAM | Max Model Size | Cost |
|--------|----------|------|----------------|------|
| `local` (default) | RTX A5000 | 24 GB | ~1.7B with LoRA | Free |
| `flash` | RunPod B200 / H200 | 192 GB | 7B–70B | Pay-per-second |

**Flash** uses the RunPod serverless Python SDK — no Docker, no SSH, no rsync overhead.
It is the recommended path for any model larger than 1.7B.

> **Note**: Flash replaces `/ops-runpod` for all training paths.
> `/ops-runpod` is retained for persistent inference servers only.

### GPU types on Flash

| GPU | VRAM | Notes |
|-----|------|-------|
| `B200` | 192 GB HBM3e | Fastest option; 3–5× H200 on MoE and long-context workloads |
| `H200` | 192 GB HBM3 | Good availability; solid baseline for 7B–13B training |

Billing: pay-per-second, 7-day execution maximum per job.

### Flash cost estimates (approximate)

| Model Size | GPU | Est. Training Time | Est. Cost |
|------------|-----|--------------------|-----------|
| 7B QLoRA SFT | B200 | ~1–2 hrs | ~$5–15 |
| 7B QLoRA SFT | H200 | ~2–3 hrs | ~$8–20 |
| 13B QLoRA SFT | B200 | ~2–4 hrs | ~$10–25 |
| 13B QLoRA SFT | H200 | ~3–5 hrs | ~$12–30 |

> Actual cost depends on dataset size and GRPO steps. Always run `estimate` first.

### Flash examples

```bash
# Estimate cost before committing
./run.sh estimate --task qra-validator --target flash --gpu B200 --size 7B

# Train 7B model on RunPod B200 (fastest)
./run.sh train --task qra-validator --target flash --gpu B200 --size 7B

# Train 13B with GRPO on H200
./run.sh train --task taxonomy-assessor --target flash --gpu H200 --size 13B --grpo-steps 2000

# SFT-only on B200
./run.sh train --task stress-test-grader --target flash --gpu B200 --size 7B --sft-only
```

## TaskSpec

Tasks are defined by YAML files in `data/tasks/`. See `task_spec.py` for the full schema.

## Common Mistakes

### WRONG: Training with fewer than 1,000 examples
```bash
./run.sh train --task stress-grading --sft-only  # only 246 samples → 33.7% shadow agreement
```

### RIGHT: Verify data volume before training
```bash
./run.sh prepare --task stress-grading --input raw.jsonl
# Check output: "1,247 training examples" → proceed
# If < 1,000: stay at Tier 2, harvest more teacher labels via /assistant-lab
```

### WRONG: Hand-crafting system prompts in JSONL training data
```json
{"messages": [{"role": "system", "content": "You are a validator..."}]}
```

### RIGHT: Validate prompts through /prompt-lab first
```bash
.pi/skills/prompt-lab/run.sh eval --prompt validator_v1 --model deepseek
# Only after prompt-lab validation → bake into training JSONL
```

### WRONG: Evaluating on the training set instead of holdout
```bash
./run.sh evaluate --task qra-validator  # evaluates on training split
```

### RIGHT: Always evaluate on held-out test set
```bash
./run.sh evaluate --task qra-validator --holdout
```

## Integration

- **`/gpt-lab`**: Benchmark and compare models trained by this skill
- **`/scillm`**: Confidence routing escalates low-confidence results to Chutes
- **`/create-intent-map`**: GRPO and reward patterns adapted from this skill
- **`/create-classifier`**: Iterative training and holdout gate patterns
