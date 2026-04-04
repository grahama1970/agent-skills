# Intervention Controls

Session: session-1774535454

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `T1`: Fix ESA HTML descriptions — extract text content (subagent-service/fix)
- `T2`: Generate ESA QRAs (137 controls × 3 = ~411 QRAs) (subagent-service/fix)
- `T3`: Complete hybrid relationship rescoring (131K relationships) (subagent-service/fix)
- `T4`: Compute per-control quality scores (subagent-service/fix)
