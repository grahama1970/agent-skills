---
name: ops-chutes
description: >
  Manage Chutes.ai resources, tracking quota usage and API health.
  Integrates with scheduler to pause operations when budget is exhausted methods.
triggers:
  - check chutes
  - chutes usage
  - chutes budget
  - chutes status
  - check chutes health
  - chutes api check
metadata:
  short-description: Chutes.ai API management and quota tracking
---

# Ops Chutes Skill

Manage Chutes.ai resources and enforce budget limits using real quota tracking.

## Triggers

- "Check chutes status" -> `status`
- "How much chutes budget left?" -> `usage`
- "Is chutes working?" -> `sanity`

## Commands

```bash
# Check model status (hot/cold/down)
./run.sh status

# Check usage against quota for a specific chute
./run.sh usage --chute-id <chute_id>

# Run sanity check (inference)
./run.sh sanity --model <model_name>

# Check budget (exit code 1 if exhausted) - for scheduler
./run.sh budget-check --chute-id <chute_id>
```

## Environment Variables

| Variable             | Description                         |
| -------------------- | ----------------------------------- |
| `CHUTES_API_TOKEN`   | API Token for authentication        |
| `CHUTES_DAILY_LIMIT` | Daily request limit (default: 5000) |
