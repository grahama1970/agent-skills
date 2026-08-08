---
name: assistant
description: >
  Shared GPT + classifier inference gateway for persona monitor tasks.
  Routes validation and classification through a 4-tier cascade:
  heuristic → classifier → local GPT → scillm.
internal: true
triggers:
  - validate
  - classify
  - assistant validate
  - assistant classify
allowed-tools:
  - Bash
  - Python
metadata:
  short-description: Shared GPT + classifier inference gateway
env:
  - ASSISTANT_MODELS_DIR (default: ~/.pi/models)
  - ASSISTANT_METRICS_DIR (default: ~/.pi/assistant)

provides:
  - assistant
composes:
  - assistant-lab
  - monitor-skills
  - scillm
  - memory
  - task-monitor
  - agentic-evals
disciplines:
  - model-ops
  - ml-training
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# assistant

Shared GPT + classifier + regressor inference gateway for persona monitor tasks.

The "warm pond" — /assistant can autonomously evolve its inference stack via
`/assistant-lab` (self-improvement workbench: create-*, *-lab, model factory)
while `/monitor-skills` provides observability across the skill ecosystem.

## Prompt Iteration Rule (NON-NEGOTIABLE)

All system prompts for `/assistant` models MUST be iterated through `/prompt-lab` before being baked into training data via `/create-gpt`. NEVER hand-craft system prompts in Python strings.

- New model prompt → `/prompt-lab eval` against ground truth first
- Prompt plateau (80-90% shadow agreement) → `/prompt-lab compare` across variants
- Model retraining → validate prompt with `/prompt-lab find-minimum` before `/create-gpt`

## Tier Cascade

| Tier | Method | Cost | Latency | Created By |
|------|--------|------|---------|------------|
| 0 | Heuristic (regex/keyword/schema) | free | microseconds | hand-coded |
| 0.5 | Classifier (DistilBERT/sklearn) | free | 5-25ms | /create-classifier |
| 0.75 | Regressor (sklearn/XGB) | free | 5-10ms | /create-regressor |
| 1.5 | Shared GPT (Qwen3-0.6B GGUF) | free | ~200ms | /create-gpt |
| 2 | scillm (DeepSeek V3.2 via Chutes) | $0.12/1K | 2-5s | persona teacher |

## Model Lifecycle (Warm Pond)

```
Tier 2 persona teacher creates labels
    ↓ harvest.py extracts shadow.jsonl
    ↓
ModelFactory.auto_improve(task)
    ↓ reads shadow agreement rate
    ├─ >= 90%: promote (shadow_mode → false)
    ├─ 80-90%: plateau → /prompt-lab redesign
    ├─ 70-80%: /create-gpt or /create-classifier retrain
    └─ < 70%: aggressive retrain + architecture change
    ↓
/gpt-lab benchmark or /classifier-lab evaluate
    ↓ passing? → promote to registry
    ↓
/monitor-skills detects drift or health issues
    ↓
/assistant-lab auto-improve (diagnose → train → eval → promote)
```

## Usage

```bash
# Validate data through tier cascade
./run.sh validate --task qra-assessor --scope brandon_bailey --input '{"question":"...", "answer":"..."}'

# Classify text
./run.sh classify --task bridge-tagger --text "satellite vulnerability assessment"

# Register a new model
./run.sh register --task NAME --model-path PATH --type gpt|classifier --threshold 0.85

# Show registered models, hit rates, tier distribution
./run.sh status

# Run synthetic input through all tiers
./run.sh self-test

# Extract tier-2 escalations as training data
./run.sh harvest --since 24h
```

## Python API

```python
from assistant import validate, classify

# Validate with 4-tier cascade
result = validate(
    input_data={"question": "What is CWE-79?", "answer": "Cross-site scripting..."},
    task="qra-assessor",
    scope="brandon_bailey",
)
print(result.tier, result.confidence, result.result)

# Classify with 3-tier cascade
result = classify(
    text="satellite vulnerability assessment",
    task="bridge-tagger",
)
print(result.prediction, result.confidence, result.source)
```

## Contract

- **Input**: Task-specific dict (validators) or text string (classifiers)
- **Output**: `GatewayResult` or `ClassifyResult` with tier, confidence, latency
- **Dependencies**: loguru, typer; optional: llama-cpp-python, torch, joblib
- **Metrics**: Appends JSONL to `~/.pi/assistant/metrics.jsonl`

## Model Factory

```bash
# Check what models a task needs
./run.sh factory needs --task stress-test-grader

# Train a GPT from harvested teacher labels
./run.sh factory train-gpt --task stress-test-grader

# Evaluate via /gpt-lab
./run.sh factory evaluate --task stress-test-grader --type gpt

# Promote a passing model (disables shadow mode)
./run.sh factory promote --task stress-test-grader --type gpt

# Autonomous improvement loop (decide + train + eval + promote)
./run.sh factory auto-improve --task stress-test-grader
```

```python
from model_factory import ModelFactory

factory = ModelFactory()
result = factory.auto_improve("stress-test-grader")
# → reads shadow agreement, trains/evals/promotes as needed
```

## Key Behaviors

1. **Lazy model loading**: Weights loaded on first call, cached in-process
2. **Memory injection**: Recalls from persona scope, prepends to GPT system prompt
3. **Passthrough mode**: Falls directly to scillm if no local model exists
4. **Shadow mode**: Tasks with `"shadow_mode": true` run local model AND scillm in parallel, log disagreements to `shadow.jsonl`, return the teacher (scillm) result. Enables safe ramp-up of new student models.
5. **Harvest**: Nightly extraction of tier-2 escalations as teacher labels
6. **Model Factory**: Via `/assistant-lab`, autonomously trains, evaluates, and promotes models when shadow mode shows a task needs improvement
7. **Warm Pond**: `/monitor-skills` watches the ecosystem (observability), `/assistant-lab` fixes problems (self-improvement). Together they form the warm pond where /assistant evolves.

## Common Mistakes

### WRONG: Hand-crafting system prompts in Python strings
```python
SYSTEM_PROMPT = "You are a QRA validator. Check if the answer is correct..."
```

### RIGHT: Iterate prompts through /prompt-lab before baking into training data
```bash
.pi/skills/prompt-lab/run.sh eval --prompt qra_validator_v1 --model deepseek
# Only after prompt-lab validation → create training data
```

### WRONG: Training with insufficient data (< 200 samples per class)
```bash
./run.sh factory train-gpt --task sparta-intent  # 50 samples, 12 classes = 4/class!
```

### RIGHT: Stay at Tier 2 and harvest more teacher labels first
```bash
./run.sh harvest --since 7d  # accumulate shadow labels
./run.sh status              # check sample counts before training
```

### WRONG: Skipping shadow mode and promoting untested models
```bash
./run.sh factory promote --task stress-test-grader  # no shadow comparison!
```

### RIGHT: Run shadow mode, verify agreement rate, then promote
```bash
./run.sh factory auto-improve --task stress-test-grader
# auto-improve reads shadow agreement rate and decides
```
