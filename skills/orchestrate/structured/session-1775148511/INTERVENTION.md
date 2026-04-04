# Intervention Controls

Session: session-1775148511

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Fix calculator bugs (add, subtract, divide) (code-runner/main)
- `2`: Fix formatter bugs (name, currency, list) (code-runner/main)
- `3`: Run full test suite (local/main)
- `4`: Lint check (local/main)
- `5`: Create integration test for edge cases (code-runner/main)
