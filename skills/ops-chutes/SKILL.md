---
name: ops-chutes
description: >
  Manage Chutes.ai resources, track 5000/day API limit, and monitor model health.
  Integrates with scheduler; budget gating is best-effort unless explicit usage source is provided and RateLimit headers may not be present.
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

# Show configured usage limit and reset time (best-effort; exact remaining not guaranteed)
./run.sh usage

# Run sanity check (inference)
./run.sh sanity --model <model_name>

# Budget gate (exit 1 if exhausted) - requires CHUTES_BUDGET_FILE or external counter; file must contain non-negative integer
./run.sh budget-check
```

## Environment Variables

| Variable             | Description                                                    |
| -------------------- | -------------------------------------------------------------- |
| `CHUTES_API_TOKEN`   | API Token for authentication                                   |
| `CHUTES_DAILY_LIMIT` | Daily request limit (default: 5000)                            |
| `CHUTES_BUDGET_FILE` | (Optional) Path to file containing integer count of used calls |
