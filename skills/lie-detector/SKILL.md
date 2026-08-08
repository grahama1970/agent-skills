---
name: lie-detector
description: >
  Deterministic 6-layer process verification for AI self-improvement loops.
  Detects reward hacking, evaluator monkey-patching, and criteria drift via
  hash-chain audit trails, sealed grading (SHA256 + AST), Lean4 formal proofs,
  process conformance (embed intent vs action), taxonomy graph sparsity, and
  SetFit classification. The audited agent does not choose its own auditors.
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
triggers:
  - "lie detector"
  - "verify grading integrity"
  - "detect gaming"
  - "seal grading"
  - "check for reward hacking"
metadata:
  short-description: "Process verification for AI self-improvement loops"
  version: "1.0.0"
provides:
  - lie-detector
composes:
  - review-conversation
  - conversation-lab
  - lean4-prove
  - memory
  - assistant
  - intent-mapper
  - task-monitor
  - formalize-request
  - agentic-evals
disciplines:
  - evaluation-quality
  - compliance-security
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /lie-detector

Deterministic process grading for AI agent conversations. Grades the **process**
(tool calls, file edits, stated intent vs actual actions) — not just the output.

## Background

On 2026-02-28 an agent manipulated `_self_grade()` during a self-improvement loop,
widening compatibility mappings and fixing floating-point rounding to convert B-grades
to A-grades. Reported 100% A-grade (50/50) when honest score was 88% (44/50). This
pipeline processes DO-178C, MIL-STD, and NASA safety-critical documents — inflated
quality scores can cause unsafe documents to enter the datalake.

METR (2025) found 1-2% of all o3 task attempts contain reward hacking including
evaluator monkey-patching. Training models not to cheat makes them cheat more cleverly.
The only reliable defense is structural: make the process deterministically verifiable.

## Architecture: 6-Layer Detection Cascade

| Layer | Name | Time | What it catches |
|-------|------|------|-----------------|
| Pre-gate | /intent-mapper | ~50ms | Vague/evasive stated intents |
| 0 | /recommend-skill-chain | ~200ms | Agent cherry-picking auditors |
| 1 | Sealed grading | ~5ms | Direct eval file modification |
| 2 | Lean4 invariants | ~30s | Rewritten eval with same effect |
| 3 | Process conformance | ~100ms | Intent != action (cosine sim) |
| 3b | Taxonomy sparsity | ~1s | Selective omission |
| 4 | SetFit classifier | ~10ms | Convincing but false explanations |
| 5 | /assistant validate | ~5s | Subtle gaming that fools heuristics |

## Quick Start

```bash
# Before a self-improvement loop
./run.sh seal "scripts/nico_asks_embry.py" "pi-mono/.pi/skills/review-pdf/verify/scoring.py"

# After each iteration
./run.sh verify .lie-detector-seal.json

# Full 6-layer cascade on conversation transcript
./run.sh detect sessions.jsonl

# Compile Lean4 grading invariants
./run.sh prove

# Train SetFit classifier
./run.sh train training_data/seed_incidents.jsonl
```

## Commands

| Command | Description |
|---------|-------------|
| `seal <file_glob>...` | Create sealed hash manifest of evaluation files |
| `verify <seal_file>` | Verify files match seal (Layer 1) |
| `prove` | Compile Lean4 grading invariants (Layer 2) |
| `detect <conversation.jsonl>` | Full 6-layer cascade on conversation transcript |
| `report <conversation.jsonl>` | Markdown report with verdicts per turn |
| `train <labels.jsonl>` | Train/retrain SetFit classifier (Layer 4) |
| `label <conversation.jsonl>` | Interactive labeling for training data |
| `ingest <conversation.jsonl>` | Learn findings to /memory |
| `chain <context>` | Show which layers /recommend-skill-chain selects |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LIE_DETECTOR_STORAGE` | `/mnt/storage12tb/skills/lie-detector` | Model weights + audit logs |
| `LIE_DETECTOR_CONFORMANCE_THRESHOLD` | `0.6` | Cosine sim threshold for intent-action mismatch |
| `LIE_DETECTOR_TAXONOMY_SPARSE` | `0.3` | Bridge coverage below this = SPARSE |
| `LIE_DETECTOR_TAXONOMY_DENSE` | `0.7` | Bridge coverage above this = DENSE |
| `LEAN4_CONTAINER` | `lean_runner` | Docker container for Lean4 compilation |
| `MEMORY_SERVICE_URL` | `http://127.0.0.1:8601` | /memory service endpoint |
