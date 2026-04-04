# Intervention Controls

Session: session-1775229904

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Create file (local/0)
- `2`: Append to file (local/0)
- `3`: Verify chain (local/0)
