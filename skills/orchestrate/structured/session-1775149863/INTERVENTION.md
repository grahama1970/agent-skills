# Intervention Controls

Session: session-1775149863

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Fix calculator bugs (code-runner/calc)
- `2`: Fix formatter bugs (code-runner/fmt)
- `3`: Full test suite (local/verify)
