---
name: review-question
description: >
  Generate, validate, and execute F36-grounded persona conversation questions.
  Phase 1: Generate domain questions tied to F36 datalake categories, validate
  via 6 gates (persona alignment, F36 grounding, data answerability, naturalness,
  system leakage, difficulty). Phase 2: Execute full conversation threads where
  Margaret/Jennifer ask Brandon, with inline metrics per turn, saved to /memory
  and markdown for human review. Phase 3: Build deterministic evidence cases
  that prove a question is answerable before any LLM touches it.
triggers:
  - "review question"
  - "generate questions"
  - "validate questions"
  - "persona conversation"
  - "f36 grounded questions"
  - "margaret ask brandon"
  - "jennifer ask brandon"
  - "conversation thread"
  - "evidence case"
  - "build evidence case"
  - "is this question answerable"
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
provides:
  - review-question
composes:
  - memory
  - scillm
  - taxonomy
  - review-conversation
  - ops-f36-plant
  - task-monitor
  - create-figure
  - lean4-prove
  - assistant
metadata:
  short-description: "F36-grounded persona question generation + conversation execution + evidence case builder"
  version: "1.1.0"
taxonomy:
  - persona
  - f36
  - qa
  - conversation
  - evidence-case
---

## Standard Review Iteration Parameters

This `review-*` skill follows the shared contract in
`skills/.system/review-iteration-contract.md`.

Canonical parameters:

- `--max-rounds N`
- `--output-dir PATH`
- `--ask-gate`
- `--ask-model MODEL` (default `gpt-5.5`)
- `--ask-reasoning LEVEL` (default `high`)
- `--ask-timeout SECONDS`
- `--ask-focus LABELS`

When `--max-rounds > 1` is supplied, the skill must behave as a bounded
gate-producing controller or fail closed if that mode is not implemented. The
canonical gate artifact is `review_result.json` with verdict
`PASS`, `NEEDS_CHANGES`, `BLOCKED`, or `INSUFFICIENT_EVIDENCE`.

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Review Question

Generate F36-grounded questions for Margaret Chen and Jennifer Cheung to ask
Brandon Bailey, validate them through 6 quality gates, then execute full
conversation threads with inline metrics.

## Quick Start

```bash
# Generate 12 questions for Margaret
./run.sh generate --persona margaret --count 12 --output questions.json

# Validate questions (6 gates)
./run.sh validate questions.json --output review.md

# Execute conversations (Margaret asks Brandon)
./run.sh converse questions.json --output conversations/

# Full pipeline: generate + validate + converse
./run.sh run --persona margaret --count 12 --output conversations/

# Build evidence case (deterministic pre-validation)
./run.sh evidence-case -q "What countermeasures protect SV-MA-3 from CWE-287?" -o case.md

# Sanity check
./run.sh sanity
```

## Commands

| Command | Description |
|---------|-------------|
| `generate` | Generate F36-grounded questions for a persona |
| `validate` | Validate questions through 6 quality gates |
| `converse` | Execute conversation threads (persona asks Brandon) |
| `run` | Full pipeline: generate + validate + converse |
| `evidence-case` | Build deterministic evidence case (5 gates, all via /memory) |
| `review` | Show conversation results (delegates to /review-conversation) |
| `sanity` | Basic validation |

## Evidence Case Gates (Pre-Validation)

Deterministic, database-driven check that proves a question is answerable
BEFORE any persona touches it.  All DB access goes through `/memory`.

| Gate | What It Checks | Source |
|------|---------------|--------|
| **1. Extract entities** | Parse control IDs, CWEs, frameworks from question | `/memory intent` (IntentMapper cascade) |
| **2. Verify existence** | Each entity exists in `sparta_controls` | `/memory count` |
| **3. Check relationships** | Graph paths between entity pairs (1-2 hop) | `/memory count` + `/memory trace` |
| **4. Decompose** | Connected components → sub-questions if disjoint | Pure algorithm (BFS) |
| **5. Formalize + QRAs** | Count QRAs, avg grounding, lean4 check | Aggregated from Gate 2 + `/lean4-prove` |

**Classifications:**
- `ANSWERABLE` — entities exist, connected, have QRAs
- `INVALID_IDS` — entity not found in SPARTA catalog
- `NO_COVERAGE` — entities exist but zero QRAs
- `NEEDS_CLARIFICATION` — no entities or keywords extractable
- `DECOMPOSE` / `PARTIALLY_ANSWERABLE` — multiple disconnected components

## Validation Gates (Phase 1)

| Gate | What It Checks |
|------|---------------|
| **Persona alignment** | Question matches persona's domain expertise |
| **F36 grounding** | Question relates to F36 datalake categories |
| **Data answerability** | Answer exists in ArangoDB (SPARTA controls + QRAs + datalake) |
| **Naturalness** | Sounds like a real engineer asking a colleague |
| **System leakage** | No mention of QRAs, AQL, control IDs, internal concepts |
| **Difficulty classification** | Correctly labeled easy/medium/hard |

## Conversation Execution (Phase 2)

Each question becomes a full conversation thread:

1. Persona asks Brandon the question
2. Brandon responds via /memory recall + AQL
3. Inline metrics captured per turn (grounding, substance, citations)
4. If persona unsatisfied, follow-up turn (max 3 turns total)
5. Final composite score + grade

Output: Markdown thread + JSONL (compatible with /review-conversation)

## Anti-Silo

- LLM calls via `/scillm` (never direct openai)
- ArangoDB queries via `/memory` recall pipeline
- Taxonomy tagging via `/taxonomy`
- Persona profiles from YAML manifests (not hardcoded)
- F36 datalake context from `/learn-datalake` + `/ops-f36-plant`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ARANGO_URL` | `http://localhost:8529` | ArangoDB connection |
| `ARANGO_DB` | `memory` | Database name |
| `CHUTES_API_KEY` | (required for LLM) | Chutes API key |
| `F36_DATALAKE_PATH` | `/mnt/storage12tb/f36_datalake` | F36 datalake root |
