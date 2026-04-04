# Intervention Controls

Session: session-1775053651

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Add _run_threat_delta_check post-hook to learn_datalake.py (subagent-service/0)
- `2`: Add delta alert cards to ChatTab on mount (subagent-service/1)
