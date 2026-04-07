---
name: llm-eval-lab
description: Evaluate and compare LLM models for task-specific accuracy, cost, and latency. Find minimum viable model, side-by-side comparison, Agent-as-Judge verdicts.
version: 0.1.0
triggers:
  - find minimum model
  - compare models
  - model comparison
  - which model is best
  - judge models
  - evaluate models
  - model evaluation
  - benchmark models
  - model cost comparison
  - smallest model that works
  - llm eval
  - model eval
composes:
  - prompt-lab
  - scillm
provides:
  - find-minimum
  - grid-eval
  - compare
  - judge
  - models
  - seed-memory
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# LLM Eval Lab

Evaluate and compare LLM models for task-specific accuracy, cost, and latency.

Split from `/prompt-lab` to keep prompt optimization separate from model evaluation.
prompt-lab focuses on: system prompt in → optimized prompt out.
llm-eval-lab focuses on: which model is cheapest/fastest/most accurate for a given task.

## Quick Start

```bash
cd .pi/skills/llm-eval-lab

# Question-by-model comparison grid (best for finding minimum viable model)
./run.sh grid-eval -g example_qwen_comparison.json

# Grid eval with specific models and retries
./run.sh grid-eval -g my_eval.json --models "qwen2.5-3b-local,qwen3-8b-local" --max-retries 2

# Find the smallest model that meets accuracy threshold (sequential, stops early)
./run.sh find-minimum --ground-truth queryspec.json --threshold 0.80

# Compare models on the same prompt
./run.sh compare --prompt taxonomy_v1 --models "deepseek,gpt-4o"

# Deep side-by-side judging with Agent-as-Judge
./run.sh judge --prompt tactic_control_prompt --model-a deepseek --model-b qwen3-235b

# List available models with capabilities
./run.sh models

# With cost comparison across providers
./run.sh find-minimum -g queryspec.json --with-cost --num-requests 90000
```

## Commands

### grid-eval — Question-by-Model Comparison Grid

Runs ALL models against ALL questions with retries. Displays a matrix with
questions as rows, models as columns, and Pass/Fail cells. Shows retry count
and recommends the smallest model that passes everything.

```bash
./run.sh grid-eval -g example_qwen_comparison.json
./run.sh grid-eval -g my_eval.json --models "qwen2.5-3b-local,qwen3-8b-local" -r 2
./run.sh grid-eval -g my_eval.json --prompt system_prompt.txt --verbose
```

| Option | Default | Description |
|--------|---------|-------------|
| `--ground-truth, -g` | required | Ground truth JSON file |
| `--models, -m` | from file | Comma-separated model aliases |
| `--prompt, -p` | none | Optional system prompt file |
| `--max-retries, -r` | 3 | Max retries per question per model |
| `--output, -o` | auto | Save results JSON path |
| `--verbose, -v` | false | Show model outputs on failure |

**Ground truth format:**
```json
{
  "title": "My Eval",
  "models": ["qwen2.5-3b-local", "qwen3-8b-local"],
  "questions": [
    {"id": 1, "short": "Simple math", "input": "What is 6*7?", "expected": "42", "eval": "contains"}
  ]
}
```

**Eval modes:** `exact`, `contains` (default), `json_field` (field=value), `regex`, `not_empty`

**Example output:**
```
┌───┬──────────────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
│ # │ Question         │ Expected │ qwen2.5… │ qwen2.5… │ qwen3…   │ qwen3…   │
├───┼──────────────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ 1 │ Simple math      │ 42       │ Pass     │ Pass     │ Pass     │ Pass     │
│ 2 │ Multi-step word  │ 25       │ Fail     │ Pass     │ Pass/2   │ Pass     │
│ 3 │ Basic coding     │ def is…  │ Fail     │ Pass     │ Pass     │ Pass     │
├───┼──────────────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│   │ TOTAL            │          │ 7/10     │ 10/10    │ 9/10(1r) │ 10/10    │
└───┴──────────────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
Minimum viable: qwen2.5-7b (10/10, 0 retries, 7B)
```

### find-minimum — Find Smallest Accurate Model

Tests models from smallest to largest, stopping at the first model that meets your accuracy threshold.

```bash
./run.sh find-minimum --ground-truth queryspec.json --threshold 0.80
./run.sh find-minimum -g queryspec.json -t 0.80 --prefer-local
./run.sh find-minimum -g queryspec.json --with-cost --num-requests 90000
```

| Option | Default | Description |
|--------|---------|-------------|
| `--ground-truth, -g` | required | Ground truth JSON file |
| `--threshold, -t` | 0.80 | Minimum accuracy threshold |
| `--prompt, -p` | none | Optional system prompt file |
| `--prefer-local` | true | Prefer local Ollama models |
| `--max-models` | 10 | Max models to test |
| `--with-cost, -c` | false | Show cost comparison across providers |
| `--num-requests, -n` | 90000 | Batch size for cost estimate |
| `--avg-input` | 400 | Avg input tokens per request |
| `--avg-output` | 600 | Avg output tokens per request |
| `--dogpile` | false | Research fresh pricing via /dogpile |

### compare — Compare Models

Run the same prompt against multiple models and show results side-by-side.

```bash
./run.sh compare --prompt taxonomy_v1 --models "deepseek,gpt-4o,qwen3-8b-local"
```

### judge — Agent-as-Judge

Deep side-by-side comparison using a meta-model to evaluate outputs.

```bash
./run.sh judge --prompt tactic_control_prompt --model-a deepseek --model-b qwen3-235b
./run.sh judge -p qra_grounded_v1 --model-a deepseek --model-b gpt-4o --meta-model deepseek
```

### models — List Available Models

```bash
./run.sh models                        # All models
./run.sh models --cap json             # Filter by capability
./run.sh models --recommend --type taxonomy  # Show memory-based recommendations
```

### seed-memory — Seed Model Memory

```bash
./run.sh seed-memory
```

## Model Configuration

Uses `models.json` from prompt-lab (shared config):

```json
{
  "deepseek": {
    "provider": "chutes",
    "model": "deepseek-ai/DeepSeek-V3",
    "params_b": 671,
    "json_mode": true
  }
}
```

## Architecture

```
llm-eval-lab/
├── SKILL.md
├── run.sh
├── sanity.sh
├── pyproject.toml
├── llm_eval_lab.py     # Main CLI (assembles commands)
├── eval_app.py         # Shared typer app + console
├── grid_eval.py        # grid-eval command (question-by-model matrix)
├── find_minimum.py     # find-minimum command
├── judge.py            # judge + compare commands
├── models_cmd.py       # models + seed-memory commands
└── ground_truth/
    └── example_qwen_comparison.json  # Sample ground truth for grid-eval
```

Imports shared modules from prompt-lab: `llm.py`, `evaluation.py`, `config.py`, `models.json`,
`model_memory.py`, `provider_pricing.py`.

All LLM calls go through scillm at localhost:4001.
