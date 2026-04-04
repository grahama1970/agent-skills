# Intervention Controls

Session: session-1774998239

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Store discrepancy findings (production run) (local/0)
- `2`: Backfill chunk_control_edges for Requirement + Table chunks (local/0)
- `3`: Create threat delta computation script (subagent-service/1)
- `4`: Visual QA: click Detail flyout and screenshot (local/2)
