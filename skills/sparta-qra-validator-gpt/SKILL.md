---
name: sparta-qra-validator-gpt
description: >
  Automated QRA quality validation where Brandon Bailey (persona via /scillm)
  does the full assessment and the GPT learns from all of Brandon's output.
  Three-tier cascade: T0 heuristic, T1.5 trained GPT, T2 /scillm Brandon.
triggers:
  - qra validator
  - validate qra
  - qra quality
  - brandon validate
  - teacher student loop
allowed-tools: Bash, Read

provides:
  - sparta-qra-validator-gpt
composes: [task-monitor]
disciplines:
  - compliance-security
  - ml-training
  - evaluation-quality
---

# sparta-qra-validator-gpt

Automated QRA quality validation where **Brandon Bailey (persona via /scillm)
does the full assessment** — reasoning quality, taxonomy correctness, relevance,
question paraphrasing, answer paraphrasing — and **the GPT learns from ALL of
Brandon's output**.

## Prompt Iteration Rule (NON-NEGOTIABLE)

Brandon's validation assessment prompts MUST be validated through `/prompt-lab` before being baked into training data. NEVER hand-craft validator system prompts in Python strings.

- Before training: `/prompt-lab eval` the validator prompt against ground truth
- Comparing variants: `/prompt-lab compare` across models

## The Flow

```
Brandon (persona via /scillm)
  │
  ├── Grades stratified random sample of QRAs
  │   ├── Structural: anchoring, grounding, citations, space terms
  │   ├── Semantic: reasoning quality, taxonomy correctness, relevance
  │   └── Augmentation: similar questions, paraphrased answer
  │
  ├── If sample passes → GPT trains on Brandon's grades
  │
  └── GPT validates the REST of the QRAs
      │
      ├── High confidence (>0.85) → Accept GPT result
      └── "Maybe" grey area (<0.85) → Escalate to /scillm Brandon
```

## What Brandon Assesses (Teacher Output)

Brandon's full assessment includes ALL of these dimensions:

| Dimension | Type | What Brandon Checks |
|-----------|------|---------------------|
| `grade` | PASS/WARN/FAIL | Overall quality grade |
| `reasoning_sound` | boolean | Is the reasoning chain logically sound? Not circular or meta-commentary? |
| `taxonomy_correct` | boolean | Do conceptual/tactical tags MATCH the actual answer content? |
| `relevance_score` | 0.0-1.0 | Is this a meaningful question a practitioner would ask? |
| `anchoring_ok` | boolean | Does answer reference the specific control by name? |
| `space_terms_ok` | boolean | Uses >= 2 framework-specific terms? |
| `grounding_check` | 0.0-1.0 | Answer grounded in sources, not hallucinated? |
| `similar_questions` | list[str] | 2-3 alternative phrasings of the question |
| `paraphrased_answer` | string | Rewritten answer preserving technical accuracy |
| `issues` | list[str] | Specific issues found |
| `rationale` | string | Brief explanation of the grade |

The GPT learns to produce ALL of these fields from Brandon's labels.

## Architecture

```
QRA from pipeline ──► Tier 0 (heuristic)
                         │
                    structural check only
                    (length, citations, tags exist)
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
          FAIL        WARN/PASS   PASS
          (stop)      (continue)  (continue)
                         │
                    ──► Tier 1.5 (trained GPT)
                         │  ~200ms, free
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
         confident   "maybe"    confident
         (accept)    (<0.85)    (accept)
                         │
                    ──► Tier 2 (/scillm Brandon)
                         │  ~3s, $0.12/1K
                         │
                    definitive grade
                    (including paraphrases)
```

## Teacher-Student Loop

Brandon (via /scillm) acts as teacher. The GPT is the student.

1. Brandon validates a **stratified random sample** (by framework)
2. Brandon's output includes ALL dimensions: grade, reasoning, taxonomy, relevance, paraphrases
3. If sample passes → GPT trains on Brandon's grades via `/create-gpt`
4. Student GPT handles 100% of items, teacher validates N%
5. Agreement tracked over time (on grade + reasoning_sound + taxonomy_correct)
6. Sample rate anneals as agreement improves (10% → 5% → 3% → 2% → 1%)
7. If disagreement exceeds threshold → trigger retraining via `/create-gpt`
8. **"Maybe" grey areas** (GPT confidence < 0.85) → escalate to `/scillm` Brandon

## Commands

```bash
# Structural checks only (Tier 0, no model needed, no API calls)
./run.sh heuristic --run-id run-recovery-verify [--limit 1000]

# Full validation: GPT + Brandon escalation for grey areas
./run.sh validate --run-id run-recovery-verify [--limit 1000] [--threshold 0.85]

# Teacher-student loop (recommended for production)
./run.sh validate-loop --run-id run-recovery-verify [--limit 1000]

# Check teacher-student agreement status
./run.sh status

# Export disagreements for retraining
./run.sh export-disagreements [--output disagreements.jsonl]

# Trigger retraining via /create-gpt
./run.sh retrain
```

## Integration

| Component | Location |
|-----------|----------|
| Trained model (GGUF) | `/mnt/storage12tb/media/agents/shared/create-gpt/models/qra-assessor/model.gguf` |
| TaskSpec | `/mnt/storage12tb/media/agents/shared/create-gpt/data/tasks/qra-assessor.yaml` |
| InferenceRouter | `graph_memory.llm.router.qra_assess_router()` |
| TeacherStudentLoop | `graph_memory.llm.teacher_student.TeacherStudentLoop` |
| Brandon gold labels | `/mnt/storage12tb/media/agents/shared/create-gpt/data/raw/qra-assessor-brandon.jsonl` |
| Teacher-student state | `data/state/qra-assessor/` |
| Reward function | `create-gpt/scripts/rewards/qra_assessor_reward.py` |

## Quality Gate Integration

At every 10K QRA checkpoint in the SPARTA pipeline:

```bash
# 1. Run automated GPT validation with Brandon escalation (~3 min for 10K)
./run.sh validate-loop --run-id run-recovery-verify --limit 10000

# 2. Review results (includes semantic quality stats)
./run.sh status

# 3. If issues found, run full Brandon review
/sparta-review assess --run-id run-recovery-verify --full
```

## Semantic vs Structural Checks

| Check | Tier 0 (Heuristic) | Tier 1.5 (GPT) | Tier 2 (Brandon) |
|-------|-------------------|-----------------| ------------------|
| Length/format | Yes | Yes | Yes |
| Citations exist | Yes | Yes | Yes |
| Tags exist | Yes | Yes | Yes |
| Anchoring | Yes | Yes | Yes |
| **Reasoning quality** | No | **Yes** | **Yes** |
| **Taxonomy correctness** | No | **Yes** | **Yes** |
| **Relevance/usefulness** | No | **Yes** | **Yes** |
| **Similar questions** | No | **Yes** | **Yes** |
| **Paraphrased answer** | No | **Yes** | **Yes** |

## Pre-Training Mode

Before the model is trained, the skill operates in **heuristic + Brandon** mode:
- Tier 0 heuristics run on all QRAs (structural checks only)
- Brandon (via /scillm) validates a stratified sample (full semantic assessment)
- Labels collected for training data (including paraphrases)
- Once enough labels exist, trigger `/create-gpt iterate --task qra-assessor`

## Environment

| Variable | Description |
|----------|-------------|
| `QRA_VALIDATOR_MODEL` | Path to GGUF model (optional, falls back to Brandon-only) |
| `QRA_VALIDATOR_THRESHOLD` | Confidence threshold for "maybe" escalation (default: 0.85) |
| `CHUTES_API_KEY` | Required for Brandon (SciLLM) validation |
