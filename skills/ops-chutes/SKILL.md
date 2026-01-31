---
name: ops-chutes
description: >
  Manage Chutes.ai resources, track 5000/day API limit, and monitor model health.
  Integrates with scheduler to pause operations when budget is exhausted.
triggers:
  - check chutes
  - chutes usage
  - chutes budget
  - chutes status
  - check chutes health
  - chutes api check
metadata:
  short-description: Chutes.ai API management and budget tracking
---

# Ops Chutes Skill

Manage Chutes.ai resources and enforce budget limits.

## Triggers

- "Check chutes status" -> `status`
- "How much chutes budget left?" -> `usage`
- "Is chutes working?" -> `sanity`

## Commands

```bash
# Check model status (hot/cold/down)
./run.sh status

# Check usage against 5000/day limit
./run.sh usage

# Run sanity check (inference)
./run.sh sanity --model <model_name>

# Check budget (exit code 1 if exhausted) - for scheduler
./run.sh budget-check
```

## Environment Variables

| Variable             | Description                         |
| -------------------- | ----------------------------------- |
| `CHUTES_API_TOKEN`   | API Token for authentication        |
| `CHUTES_DAILY_LIMIT` | Daily request limit (default: 5000) |
