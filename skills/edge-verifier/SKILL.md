---
name: edge-verifier
description: >
  Verifies relationships between a source text (e.g. Episode, Task) and existing Knowledge Graph lessons.
  Runs KNN/Hybrid search to find candidates, then uses LLM (scillm) to verify "verifies", "contradicts",
  or "related" stances with strict rationales.
internal: true
allowed-tools: Bash
triggers:
  - verify edges
  - link content
  - generate relationships
  - schedule verification
metadata:
  short-description: KNN + LLM verification for KG edges
provides:
  - edge-verification
composes:
  - scillm
  - task-monitor
  - agentic-evals
taxonomy:
  - validation
  - knowledge
  - precision
disciplines:
  - memory-knowledge
  - evaluation-quality
---

# Edge Verifier

This skill links new content to the existing Knowledge Graph by:

1.  **Recall**: Running a KNN/Hybrid search (`graph_memory.search`) to find potential related lessons.
2.  **Verify**: Using `scillm` (LLM) to audit the relationship, classifying it as `verifies`, `contradicts`, or `neutral`.
3.  **Link**: Creating verified `lesson_edges` in ArangoDB.

## Usage

### Manual Execution

```bash
# Verify edges for a specific source text
.pi/skills/edge-verifier/run.sh --source_id <ID> --text "Content to verify..."

# With explicit options
.pi/skills/edge-verifier/run.sh --source_id <ID> --text "..." --type "episode_turn"
```

## Scheduling (Scheduler Integration)

This skill is designed to be scheduled via the `/scheduler` skill for continuous verification of new memory artifacts.

### Register with Scheduler

```bash
.pi/skills/scheduler/run.sh register \
  --name "edge-verify-nightly" \
  --cron "0 2 * * *" \
  --command ".pi/skills/edge-verifier/run.sh --batch" \
  --description "Nightly edge verification"
```

Jobs and logs are stored under `~/.pi/scheduler/`. See `.pi/skills/scheduler/SKILL.md` for full options.

## Common Mistakes

### WRONG: Running verification without ArangoDB credentials
```bash
./run.sh --source_id <ID> --text "content"  # fails silently without .env
```

### RIGHT: Ensure .env has ArangoDB and Chutes credentials
```bash
# Verify .env exists with ARANGO_URL, ARANGO_DB, CHUTES_API_KEY
cat .env | grep -E "ARANGO|CHUTES"
./run.sh --source_id <ID> --text "content"
```

### WRONG: Verifying edges without specifying content type
```bash
./run.sh --source_id <ID> --text "content"  # default type may not match
```

### RIGHT: Specify the source type for accurate classification
```bash
./run.sh --source_id <ID> --text "content" --type "episode_turn"
```

### WRONG: Running batch verification during peak hours
```bash
./run.sh --batch  # competes with interactive queries for LLM slots
```

### RIGHT: Schedule batch verification for off-peak (nightly)
```bash
.pi/skills/scheduler/run.sh register --name "edge-verify-nightly" \
  --cron "0 2 * * *" --command ".pi/skills/edge-verifier/run.sh --batch"
```

## Prerequisites

- `.env` must expose ArangoDB credentials.
- `CHUTES_API_KEY` for LLM calls.
