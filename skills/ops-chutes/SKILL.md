---
name: ops-chutes
description: >
  Manage Chutes.ai resources, tracking Account Balance and API health.
  Integrates with scheduler to pause operations when balance is low.
triggers:
  - check chutes
  - chutes usage
  - chutes budget
  - chutes status
  - check chutes health
  - chutes api check
metadata:
  short-description: Chutes.ai API management and Balance tracking
---

# Ops Chutes Skill

Manage Chutes.ai resources and enforce budget limits using Account Balance.

## Triggers

- "Check chutes status" -> `status`
- "How much chutes budget left?" -> `usage`
- "Is chutes working?" -> `sanity`

## Commands

```bash
# Check model status (hot/cold/down) - Management API required
./run.sh status

# Check Account Balance (and optional specific quota)
./run.sh usage [--chute-id <id>]

# Run sanity check (Inference via Qwen/Qwen2.5-72B-Instruct)
./run.sh sanity --model <model_name>

# Check budget (exit 1 if Balance < MIN_BALANCE or Quota exhausted)
./run.sh budget-check [--chute-id <id>]
```

## Environment Variables

| Variable             | Description                               |
| -------------------- | ----------------------------------------- |
| `CHUTES_API_TOKEN`   | API Token for authentication              |
| `CHUTES_DAILY_LIMIT` | (Deprecated) Daily request limit          |
| `CHUTES_MIN_BALANCE` | Minimum balance threshold (default: 0.05) |
