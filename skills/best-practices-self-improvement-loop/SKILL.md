---
name: best-practices-self-improvement-loop
description: >
  Deterministic coded self-improvement loops for *-lab skills.
  The agent will NOT do this reliably — loops MUST be in code.
  Proven pattern from Classifier Lab: data_enrichment.py + training_loop.py.
triggers:
  - self-improvement loop
  - self improvement
  - improvement loop
  - iterate until gate
  - retry loop
  - coded loop
  - deterministic loop
  - compete evaluate gate retry
  - training loop best practices
  - how to write a self-improvement loop
metadata:
  short-description: Deterministic self-improvement loops — the agent won't do it, code it
provides:
  - self-improvement-pattern
  - coded-loop-template
composes:
  - classifier-lab
  - best-practices-python
taxonomy:
  - engineering
  - patterns
---

# Deterministic Self-Improvement Loops

## The Problem

The project agent will NOT reliably execute self-improvement loops on its own. Proven failure modes:

1. **Skips steps** — reports deficits without acting on them
2. **Halts early** — checks the math, says "insufficient," and waits for human direction
3. **Hallucinated results** — invents thresholds and metrics instead of running real training
4. **No retry** — tries once, fails, reports failure as final answer

This was proven in the Classifier Lab session (2026-03-29 to 2026-03-31):
- Agent reported "data insufficient" 3 times without searching HuggingFace
- Agent fabricated evaluation thresholds instead of reading eval-results.json
- Agent required human correction at every step to continue the loop
- Once the loops were coded as scripts, they ran correctly every time

## The Rule

**ALL self-improvement loops MUST be coded as deterministic scripts.**

The agent's role is to invoke the script, not to be the script.

## The Pattern

Every *-lab skill that has a compete → evaluate → gate → retry cycle uses this pattern:

```
┌─────────────────────────────────────────────┐
│  PRE-FLIGHT CHECK (deterministic)           │
│  Can we even attempt this? Check inputs.    │
│  If no → HALT with reason                   │
└──────────────────┬──────────────────────────┘
                   │ yes
                   ▼
┌─────────────────────────────────────────────┐
│  TRY STRATEGY[i]                            │
│  Execute the current approach               │
│  Write results to disk IMMEDIATELY          │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  MEASURE against GATE                       │
│  Compare result to user-configured target   │
│  (NEVER a fabricated threshold)             │
└──────────┬───────────────┬──────────────────┘
           │ passed         │ failed
           ▼               ▼
     ┌──────────┐   ┌─────────────────────────┐
     │  DONE    │   │  MORE STRATEGIES?        │
     │  Write   │   │  i < len(strategies)     │
     │  results │   └─────┬──────────┬─────────┘
     └──────────┘         │ yes      │ no
                          ▼          ▼
                    [loop back]  ┌──────────────┐
                    to TRY      │  HALT         │
                                │  Write audit  │
                                │  trail to disk│
                                └──────────────┘
```

## The 6 Rules

### 1. The loop MUST be in code, not agent-directed

```python
# WRONG: Agent decides what to try next
# "I'll try lowering the learning rate..." → skips steps, forgets, hallucinates

# RIGHT: Script iterates through strategies deterministically
strategies = [
    {"name": "baseline", "lr": 2e-5, "epochs": 5},
    {"name": "lower_lr", "lr": 1e-5, "epochs": 5},
    {"name": "more_epochs", "lr": 2e-5, "epochs": 10},
    {"name": "regularized", "lr": 1e-5, "epochs": 10, "weight_decay": 0.1},
]

for strategy in strategies:
    result = train(strategy)
    if result.f1 >= gate:
        break
```

### 2. Each iteration: try → measure → compare to gate → adjust → retry

Every iteration has the same structure. No exceptions.

```python
for i, strategy in enumerate(strategies):
    # TRY
    result = execute_strategy(strategy)

    # MEASURE
    metric = result.get_metric(gate_metric_name)

    # COMPARE TO GATE
    if metric >= gate_threshold:
        write_success(result)
        return  # DONE

    # ADJUST (implicit — next strategy in the list)
    logger.info(f"Strategy {strategy.name}: {metric} < {gate_threshold}, trying next")
```

### 3. Strategies are ordered and exhausted deterministically

The strategy list is defined upfront. The script tries them in order. No branching, no agent judgment about which to try next.

**Classifier Lab training strategies:**
1. Baseline HPs from tune-config
2. Lower learning rate (÷2)
3. More epochs (×2)
4. Regularization (lower lr + more epochs + smaller batch)
5. Next backbone → repeat 1-4

**Classifier Lab data enrichment strategies:**
1. Search HuggingFace for matching datasets
2. Mine conversation transcripts from ArangoDB
3. Abandon with audit trail

**Prompt Lab strategies (future):**
1. Original prompt
2. Rephrase with more detail
3. Add examples (few-shot)
4. Chain-of-thought variant
5. Structured output format

### 4. Halt with full audit trail when exhausted

When all strategies are tried and the gate isn't met, the script halts and writes:

```json
{
  "status": "halted",
  "best_f1": 0.770,
  "gate_f1": 0.90,
  "total_rounds": 6,
  "results": [
    {"round": 1, "backbone": "distilbert", "strategy": "baseline", "f1": 0.764},
    {"round": 2, "backbone": "distilbert", "strategy": "lower_lr", "f1": 0.763},
    ...
  ]
}
```

The human sees what was tried, what each attempt scored, and why it stopped. Not "it didn't work" — a full audit of every attempt.

### 5. Pre-flight sufficiency check before entering the loop

Before burning GPU time or API credits, check if the inputs are viable:

```python
# Data sufficiency (Classifier Lab)
required = num_classes * min_samples_per_class  # deterministic arithmetic
if available < required:
    halt("Need {required} samples, have {available}")

# Prompt viability (Prompt Lab — future)
if not prompt_template:
    halt("No prompt template defined")

# Model availability (LLM Eval Lab — future)
if not any(model_available(m) for m in models):
    halt("No models accessible")
```

This is arithmetic, not LLM judgment. The only exception is Research tab readiness, which requires one LLM call to assess whether the research output is sufficient to proceed.

### 6. Results written to disk after every iteration

Not at the end. After EVERY iteration. If the script crashes mid-loop, the results so far are preserved.

```python
for strategy in strategies:
    result = execute_strategy(strategy)

    # Write IMMEDIATELY — before checking gate
    all_results.append(result)
    write_json(output_path / "benchmark.json", {
        "results": all_results,
        "best_f1": max(r["f1"] for r in all_results),
        "status": "in_progress",
    })

    if result.f1 >= gate:
        break
```

## Reference Implementations

### Classifier Lab (working, tested)

| Script | Purpose | Location |
|--------|---------|----------|
| `data_enrichment.py` | Search HF → mine transcripts → abandon | `.pi/skills/classifier-lab/scripts/` |
| `training_loop.py` | 4 HP strategies × N backbones → halt | `.pi/skills/classifier-lab/scripts/` |
| `pipeline.py` | Wires enrichment + training together | `.pi/skills/classifier-lab/scripts/` |

### Prompt Lab (planned)

The same pattern applies: coded script that tries prompt variations in order, measures against an eval gate, and halts with an audit trail.

### LLM Eval Lab (planned)

Model comparison loop: try N models, score each, select winner or halt.

## Anti-Patterns

| Anti-Pattern | Why It Fails | Fix |
|-------------|-------------|-----|
| Agent decides next strategy | Skips steps, forgets, hallucinates | Coded strategy list |
| Agent reports deficit without acting | Lazy — checks math, waits | Script searches HuggingFace automatically |
| Fabricated thresholds | "15% error rate" — where did that come from? | Only user-configured gates |
| Results written only at end | Crash loses all progress | Write after every iteration |
| No pre-flight | Burns GPU on impossible task | Arithmetic check first |
| Agent-directed retry | "I'll try lowering LR..." | Script has ordered strategy list |

## How to Create a New Loop

1. Define the **gate**: what metric, what threshold (from user config, not invented)
2. Define the **strategies**: ordered list of approaches to try
3. Define the **pre-flight**: what must exist before the loop starts
4. Write a Python script with the pattern above
5. Wire into the UX via a POST endpoint
6. Test with a project that FAILS the gate to verify the loop actually retries

The test that matters is not "does it pass?" — it's "does it correctly try everything and halt with an audit trail when nothing works?"
