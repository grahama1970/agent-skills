---
name: ops-chutes
description: >
  Manage Chutes.ai resources, tracking Pro Plan Daily Usage and Account Balance.
  Integrates with scheduler to pause operations when daily limit (5000) is reached.
triggers:
  - check chutes
  - chutes usage
  - chutes budget
  - chutes status
  - check chutes health
  - chutes api check
metadata:
  short-description: Chutes.ai API management and Daily Usage tracking
---

# Ops Chutes Skill

Manage Chutes.ai resources and enforce 5000 calls/day limit.

## Triggers

- "Check chutes status" -> `status`
- "How much chutes budget left?" -> `usage`
- "Is chutes working?" -> `sanity`

## Commands

```bash
# Check model status (hot/cold/down) - Management API required
./run.sh status

# Check Daily Usage (Pro Plan) and Account Balance
./run.sh usage

# Run sanity check (Inference via Qwen/Qwen2.5-72B-Instruct)
./run.sh sanity --model <model_name>

# Check budget (exit 1 if Daily Limit (5000) exhausted OR Balance low)
./run.sh budget-check
```

## Environment Variables

| Variable             | Description                               |
| -------------------- | ----------------------------------------- |
| `CHUTES_API_TOKEN`   | API Token for authentication              |
| `CHUTES_DAILY_LIMIT` | Daily call limit (default: 5000)          |
| `CHUTES_MIN_BALANCE` | Minimum balance threshold (default: 0.05) |
