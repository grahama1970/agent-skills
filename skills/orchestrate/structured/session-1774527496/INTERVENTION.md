# Intervention Controls

Session: session-1774527496

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `T1`: Stand up /taxonomy daemon endpoints (subagent-service/infra)
- `T2`: Enrich ESA control descriptions via Brave Search (subagent-service/enrich)
- `T3`: Enrich NASA control descriptions via Brave Search (subagent-service/enrich)
- `T4`: Generate QRAs for SPARTA countermeasures (90 controls) (subagent-service/generate)
- `T5`: Generate QRAs for SPARTA techniques (216 controls) (subagent-service/generate)
- `T6`: Generate QRAs for ISO 27001 controls (15 controls) (subagent-service/generate)
- `T7`: Generate QRAs for ESA controls (137 controls) (subagent-service/generate)
- `T8`: Generate QRAs for NASA controls (14 controls) (subagent-service/generate)
- `T9`: Recompute relationship scores via Mind tag Jaccard intersection (subagent-service/score)
- `T10`: Compute per-control quality score (subagent-service/score)
- `T11`: Run /data-audit for coverage report (subagent-service/verify)
- `T12`: UI verification — status badges + chat cascade + screenshots (subagent-service/verify)
