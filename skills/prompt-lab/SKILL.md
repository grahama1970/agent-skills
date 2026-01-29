---
name: prompt-lab
description: >
  Iterate on LLM prompts with structured evaluation and self-correction.
  Test prompts against ground truth, compare models, track version history.
  Self-correction loop sends invalid outputs back to LLM for fixing.
allowed-tools: ["Bash", "Read", "Write"]
triggers:
  - prompt-lab
  - eval prompt
  - test prompt
  - compare models
  - iterate prompt
  - prompt evaluation
  - prompt-validator
metadata:
  short-description: Iterate and evaluate LLM prompts with self-correction
---

# Prompt Lab

Systematic prompt engineering with ground truth evaluation and **self-correction loop**.

## Key Feature: Self-Correction Loop

Unlike simple validation that silently filters invalid outputs, this skill:

1. **Presents vocabulary in prompt** - LLM knows valid options upfront
2. **Validates response** - Pydantic catches invalid tags
3. **Sends correction back to LLM** - "You used invalid tags X. Valid options are Y. Please fix."
4. **Tracks correction rounds** - Metrics show how often LLM needed help

This gives the model a chance to self-correct rather than silently failing.

## Quick Start

```bash
cd /home/graham/workspace/experiments/pi-mono/.pi/skills/prompt-lab

# Run evaluation with self-correction enabled (default)
./run.sh eval --prompt taxonomy_v1 --model deepseek

# Compare multiple models on same prompt
./run.sh compare --prompt taxonomy_v1 --models "deepseek,gpt-4o"

# Interactive iteration loop (like /review-code)
./run.sh iterate --prompt taxonomy_v1 --target-f1 0.9

# View evaluation history
./run.sh history --prompt taxonomy_v1
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: LLM Call with Vocabulary in Prompt                │
│     - Vocabulary clearly defined (Tier 0, Tier 1 tags)      │
│     - JSON response format enforced                         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Stage 2: Pydantic Validation                               │
│     - Parse JSON response                                   │
│     - Detect invalid/hallucinated tags                      │
│     - Track rejected tags for metrics                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Stage 3: Self-Correction Loop (if invalid tags detected)   │
│     - Send assistant message: "Invalid tags: X"             │
│     - Ask LLM to fix: "Valid options are: Y"                │
│     - Retry up to N times (default: 2)                      │
│     - Track correction rounds in metrics                    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Stage 4: Evaluation Metrics                                │
│     - Precision/Recall/F1 vs ground truth                   │
│     - Correction rounds needed                              │
│     - Correction success rate                               │
└─────────────────────────────────────────────────────────────┘
```

## Commands

### eval - Run Evaluation

```bash
./run.sh eval --prompt taxonomy_v1 --model deepseek

# Options:
#   --prompt NAME           Prompt version to test
#   --model NAME            Model to use (deepseek, gpt-4o, etc.)
#   --cases N               Number of test cases (default: all)
#   --max-corrections N     Max self-correction rounds (default: 2)
#   --no-correction         Disable self-correction loop
#   --task-name NAME        Task-monitor task name for quality gate
#   --verbose               Show per-case details
```

### iterate - Interactive Iteration (like /review-code)

```bash
./run.sh iterate --prompt taxonomy_v1 --target-f1 0.9

# Runs evaluation → shows results → waits for prompt edit → re-runs
# Continues until target F1 reached or max rounds hit

# Options:
#   --prompt NAME           Starting prompt version
#   --model NAME            Model to use
#   --max-rounds N          Maximum iteration rounds (default: 5)
#   --target-f1 FLOAT       Target F1 score to stop (default: 0.9)
```

### compare - Compare Models

```bash
./run.sh compare --prompt taxonomy_v1 --models "deepseek,gpt-4o"

# Output:
# | Model    | F1    | Corrections | Time  |
# |----------|-------|-------------|-------|
# | deepseek | 0.90  | 3           | 2.3s  |
# | gpt-4o   | 0.93  | 1           | 1.1s  |
```

### history - View History

```bash
./run.sh history --prompt taxonomy_v1

# Shows all evaluation runs with scores over time
```

### analyze - Analyze Past Results

```bash
./run.sh analyze --prompt taxonomy_v1

# Analyzes error patterns across all previous evaluations:
# - Most common invalid tags
# - Cases needing correction
# - Performance trend over time
# - Suggests improvements based on patterns
```

### optimize - LLM-Powered Prompt Optimization

```bash
./run.sh optimize --prompt taxonomy_v1

# Uses LLM to analyze error cases and suggest prompt improvements:
# - Reviews cases with low F1 scores
# - Identifies ambiguous tag definitions
# - Generates revised prompt sections
# - Saves suggestions for review
```

## Self-Correction Prompt

When invalid tags are detected, this correction message is sent back to the LLM:

```
Your response contained invalid tags that are not in the allowed vocabulary.

Invalid tags you used: {rejected_tags}

Valid conceptual tags (Tier 0): Corruption, Fragility, Loyalty, Precision, Resilience, Stealth
Valid tactical tags (Tier 1): Detect, Evade, Exploit, Harden, Isolate, Model, Persist, Restore

Please correct your response. Return ONLY valid JSON with tags from the allowed vocabulary above.
Do NOT invent new categories. Only use the exact tag names listed.
```

## Quality Gates

Evaluation enforces quality gates:

- **F1 >= 0.8** - Must achieve 80% F1 score against ground truth
- **Correction Success >= 90%** - Self-correction must succeed 90% of the time

If quality gates fail, exit code is 1 (for CI/CD integration).

## Task-Monitor Integration

```bash
# Notify task-monitor of evaluation result
./run.sh eval --prompt taxonomy_v1 --task-name "prompt-validation"

# Task-monitor receives:
# - Task name
# - Pass/fail status
# - Metrics (F1, correction rounds, rejected tags)
```

## Directory Structure

```
prompt-lab/
├── SKILL.md
├── run.sh
├── prompt_lab.py           # Main CLI with self-correction
├── ground_truth/
│   └── taxonomy.json       # Test cases with expected outputs
├── prompts/
│   ├── taxonomy_v1.txt     # Prompt version 1
│   └── taxonomy_v2.txt     # Prompt version 2
├── results/
│   └── taxonomy_v1_deepseek_20260128.json  # Evaluation results
├── models.json             # Model configurations
└── pyproject.toml
```

## Metrics

- **F1**: Combined precision/recall across all tag types
- **Conceptual Precision/Recall**: Tier 0 tag accuracy
- **Tactical Precision/Recall**: Tier 1 tag accuracy
- **Correction Rounds**: Total self-correction attempts across all cases
- **Correction Success Rate**: Percentage of cases where self-correction worked
- **Rejected Tags**: Total hallucinated tags caught (before and after correction)

## Model Configuration

Models are configured in `models.json`:

```json
{
  "deepseek": {
    "provider": "chutes",
    "model": "deepseek-ai/DeepSeek-V3-0324-TEE",
    "api_base": "$CHUTES_API_BASE",
    "api_key": "$CHUTES_API_KEY"
  },
  "gpt-4o": {
    "provider": "openai",
    "model": "gpt-4o",
    "api_key": "$OPENAI_API_KEY"
  }
}
```

## Use Cases

1. **Taxonomy Prompt Iteration**: Improve SPARTA bridge tag extraction
2. **QRA Prompt Testing**: Test question-reasoning-answer extraction
3. **Classification Tasks**: Any structured output with controlled vocabulary
4. **Model Selection**: Compare providers for quality/cost tradeoffs
5. **Self-Correction Analysis**: Understand which models need more guidance
