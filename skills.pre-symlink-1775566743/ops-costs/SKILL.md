---
name: ops-costs
description: >
  Unified cost aggregator across all provider ops-* skills. Calls
  ops-chutes, ops-claude, ops-google, and ops-runpod, normalizes
  their JSON output into a single cost report with figure_data.
triggers:
  - cost report
  - how much am I spending
  - monthly costs
  - provider costs
  - spending breakdown
  - budget check
  - cost summary
  - total costs
  - what are my costs
  - ops costs
provides:
  - ops-costs
composes:
  - ops-chutes
  - ops-claude
  - ops-google
  - ops-runpod
  - task-monitor
---

# /ops-costs — Unified Cost Aggregator

Aggregates costs from all provider ops-* skills into a single report.

## Commands

```bash
./run.sh report [--daily|--monthly] [--days N] [--json]   # Aggregated view
./run.sh breakdown [--provider chutes|claude|google|runpod] # Single provider detail
./run.sh budget [--monthly-limit 200]                       # Alert if approaching limit
```

## Provider Integration

| Provider | Command | Returns |
|----------|---------|---------|
| ops-chutes | `run.sh report --monthly --json` | API costs per day |
| ops-claude | `run.sh report --monthly --json` | API-equivalent costs |
| ops-google | `run.sh usage --json` | Call counts (free tier) |
| ops-runpod | `run.sh list-instances` | GPU instance costs |

## JSON Output

```json
{
  "period": "2026-02",
  "providers": {
    "chutes": {"total_usd": 55.00, "source": "api"},
    "claude": {"total_usd": 200.00, "source": "max_plan_equivalent"},
    "google": {"total_usd": 0.00, "source": "free_tier", "calls": 1200},
    "runpod": {"total_usd": 45.00, "source": "gpu_hours"}
  },
  "total_usd": 300.00,
  "figure_data": {
    "bar": {"metrics": {"Chutes": 55, "Claude (equiv)": 200, "RunPod": 45}},
    "pie": {"Chutes": 55, "Claude": 200, "RunPod": 45}
  }
}
```

## Integration

- **dashboard**: Add `collect_costs()` collector reading last run
- **scheduler**: Nightly `cost-report` job
