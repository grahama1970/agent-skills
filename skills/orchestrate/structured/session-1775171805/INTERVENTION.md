# Intervention Controls

Session: session-1775171805

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Create usePostureData hook — aggregates control family stats (code-runner/0)
- `2`: Generate Posture Dashboard design via /mockup-lab (code-runner/0)
- `3`: Implement PostureDashboard.tsx — hero row (score + framework rings) (code-runner/1)
- `4`: Implement PostureDashboard — main row (family bars + gap analysis) (code-runner/1)
- `5`: Implement PostureDashboard — detail row (drift + risks) (code-runner/1)
- `6`: QuerySpec instrumentation + verify-data-qid gate (code-runner/2)
- `7`: Add family flyout — drill into controls for selected family (code-runner/2)
- `8`: Visual QA via /test-interactions (local/3)
- `9`: VLM review — compare implementation to approved design (code-runner/3)
