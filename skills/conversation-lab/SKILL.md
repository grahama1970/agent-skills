---
name: conversation-lab
description: >
  Self-improving conversation convergence loop for SPARTA stress tests.
  Diagnoses unsatisfied sessions, re-runs until personas say satisfactory,
  outputs structured JSON for /assess consumption. Use when conversation
  quality is low, sessions are partial, or you need to converge conversations.
triggers:
  - conversation lab
  - converge conversations
  - fix unsatisfied sessions
  - conversation convergence
  - diagnose conversations
  - rerun sessions
metadata:
  short-description: Conversation convergence engine
  version: "1.0.0"
provides:
  - conversation-convergence
  - session-diagnostics
  - turn-optimization
composes:
  - sparta-stress-test
  - review-conversation
  - episodic-archiver
  - task-monitor
  - memory
taxonomy:
  - validation
  - iteration
  - convergence
disciplines:
  - persona-simulation
  - evaluation-quality
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Conversation Lab

Self-improving convergence loop for SPARTA stress test conversations.
Follows the Shadow-Lego pattern: run -> assess -> diagnose -> fix -> re-run.

## Commands

| Command | Description |
|---------|-------------|
| `diagnose [file]` | Structured JSON diagnosis for `/assess` (use `--format md` for Rich tables) |
| `report [file]` | Full markdown report with conversation transcripts (like `/tmp/conversation_flows_*.md`) |
| `data [file]` | Export JSON chart data for `/create-figure` (radar, heatmap, grade distribution) |
| `converge [file]` | Re-run unsatisfied sessions until personas are happy or ceiling hit |
| `optimize` | Analyze session data + episodic archives to recommend optimal turn counts |
| `status` | Show convergence state (running/complete/stalled) |

## Usage

```bash
# Diagnose existing sessions (JSON output)
./run.sh diagnose /path/to/sessions_*.jsonl

# Run convergence on unsatisfied sessions
./run.sh converge /path/to/sessions_*.jsonl --max-cycles 3

# Dry run (no LLM calls)
./run.sh converge /path/to/sessions_*.jsonl --dry-run

# Check turn optimization from episodic data
./run.sh optimize

# Human-readable markdown report (full transcripts)
./run.sh report /path/to/sessions_*.jsonl -o /tmp/conversation_flows.md

# Export chart data for /create-figure
./run.sh data /path/to/sessions_*.jsonl -o /tmp/charts/
# Then: cd .pi/skills/create-figure && ./run.sh radar --input /tmp/charts/radar.json
```

## Task-Monitor Integration

```bash
# Progress is reported automatically during converge
cat conversation_lab_task_state.json | jq
```

## NDJSON Streaming

```bash
./run.sh converge sessions.jsonl --json-stream | tee converge_results.jsonl
```

## Convergence Logic

1. **DIAGNOSE** — Read sessions, classify failures (zero QRA, over-clarification, regression, wrong answer, coverage gap)
2. **FILTER** — Select rerun candidates (unsatisfied + rerun_eligible)
3. **RE-RUN** — Call sparta-stress-test with same seeds, higher CONVO_MAX_ROUNDS
4. **COMPARE** — Grade delta between original and new session
5. **ARCHIVE** — Feed improvements to /episodic-archiver
6. **DECIDE** — Converging? Continue. Plateau? Stop. Regressing? Rollback.

### Stopping Conditions

- `satisfied_rate >= 0.80` — 80% persona satisfaction
- `max_cycles` exhausted (default 5)
- Plateau: 2 consecutive cycles with < 5% improvement
- Budget: total LLM calls exceed threshold
