# Intervention Controls

Session: session-1774526756

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `T1`: Stand up /taxonomy daemon endpoints (subagent-service/p0)
- `T2`: Generate QRAs for SPARTA countermeasures (90 controls) (subagent-service/p0)
- `T3`: Generate QRAs for SPARTA techniques (216 controls) (subagent-service/p0)
- `T4`: Generate QRAs for ISO 27001 controls (15 controls) (subagent-service/p0)
- `T5`: Generate QRAs for ESA + NASA controls (151 controls) (subagent-service/p0)
- `T6`: Recompute relationship scores via /taxonomy intersection (subagent-service/p0)
- `T7`: Compute per-control quality score (replaces NRS) (subagent-service/p0)
- `T8`: Normalize duplicate framework entries (subagent-service/p1)
- `T9`: Run worksheets.yaml audit (04_TASKS) (subagent-service/p1)
- `T10`: Enrich ESA + NASA descriptions (if missing) (subagent-service/p1)
- `T11`: Update status badges to use quality score (subagent-service/p2)
- `T12`: Delete legacy SOURCES array from SourcesView (subagent-service/p2)
- `T13`: Live test chat cascade pipeline (subagent-service/p2)
- `T14`: Run /data-audit for full pipeline coverage report (subagent-service/p3)
- `T15`: Full headless verification + screenshots (subagent-service/p3)
