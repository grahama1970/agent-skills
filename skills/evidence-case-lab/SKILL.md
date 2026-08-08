---
name: evidence-case-lab
version: 0.2.0
description: >
  Self-improving evidence case convergence loop. Runs question banks against
  /create-evidence-case, diagnoses mismatches, and tracks convergence across cycles.
triggers:
  - evidence case lab
  - evidence case converge
  - fix evidence scoring
  - run evidence questions
metadata:
  short-description: Self-improving evidence case convergence loop
composes:
  - create-evidence-case
  - memory
  - agentic-evals
provides:
  - evidence-case-convergence
disciplines:
  - compliance-security
  - evaluation-quality
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /evidence-case-lab

Self-improving convergence loop for `/create-evidence-case`. Runs question bank,
diagnoses mismatches (false positives, false negatives, grounding failures),
re-runs, and tracks convergence across cycles.

## Commands

| Command    | Description |
|------------|-------------|
| `run`      | Run question bank, produce results.json + REPORT.md |
| `diagnose` | Classify failures from last run into error categories |
| `converge` | Full loop: run → diagnose → (human/agent adjusts) → re-run |

## Usage

```bash
# Run the full question bank
./run.sh run

# Run with custom questions file
./run.sh run --questions path/to/questions.json

# Diagnose last run
./run.sh diagnose

# Convergence loop (max 5 cycles)
./run.sh converge --max-cycles 5
```

## Error Categories

| Category | Meaning | Fix |
|----------|---------|-----|
| `false_positive` | Adversarial question got SATISFIED | Improve grounding checks |
| `false_negative` | Real question got NOT_SATISFIED | Improve recall or technique bridge |
| `grounding_failure` | FP caused by unresolved ID-like terms | Entity extraction grounding evidence |
| `technique_scatter` | Too many unrelated techniques | Improve technique bridge thresholds |

## Convergence Criteria

- Adversarial false positive rate = 0% (10/10 rejected)
- Real question SATISFIED rate >= 85% (no regression from 92.5%)
- No regressions from previous cycle
- Off-topic questions must return not_satisfied

## State Files

- `state/convergence.jsonl` — per-cycle metrics (append-only)
- `state/last_results.json` — most recent run results
- `state/eval_baseline.json` — last known good baseline
- `state/results_cycle_N.json` — per-cycle results for comparison

## Question Bank Format

```json
[
  {"id": "Q1", "question": "What SPARTA controls...", "expected": "satisfied"},
  {"id": "ADV1", "question": "How does X23-MUSTARD...", "expected": "not_satisfied"}
]
```
