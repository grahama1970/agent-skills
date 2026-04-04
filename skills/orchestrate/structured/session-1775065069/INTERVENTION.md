# Intervention Controls

Session: session-1775065069

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Add Express endpoints via /code-runner (local/0)
- `2`: Generate React components via /code-runner (local/0)
- `3`: Wire into App.tsx via /code-runner (local/1)
- `4`: Visual QA screenshot (local/1)
