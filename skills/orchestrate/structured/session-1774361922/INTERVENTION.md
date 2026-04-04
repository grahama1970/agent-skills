# Intervention Controls

Session: session-1774361922

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Stitch mockup: Binary ingestion progress panel (docker-log style) (subagent-service/0)
- `2`: SSE streaming endpoint for /analyze-elf pipeline progress (subagent-service/1)
- `3`: React IngestionProgress component (from Stitch mockup) (subagent-service/2)
- `4`: Wire IngestionProgress into Binary Explorer data panel (subagent-service/2)
- `5`: VLM review: compare implementation screenshot to Stitch mockup (subagent-service/3)
- `6`: Add ingestion tests to Binary Explorer test manifest (subagent-service/3)
