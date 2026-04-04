# Intervention Controls

Session: session-1774285499

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Create augmentation prompt template in /prompt-lab (subagent-service/0)
- `2`: Generate ~250 variations per action type via Gemini (8 batches) (subagent-service/0)
- `3`: Validate generated QuerySpecs — reject invalid JSON or unknown actions (local/1)
- `4`: Ingest validated pairs to ArangoDB via /learn (subagent-service/1)
- `5`: Apply Intent taxonomy tags via /taxonomy/batch-tag (subagent-service/2)
- `6`: Create similar_to edges between docs sharing Intent tags (subagent-service/2)
- `7`: Verification: novel phrasing accuracy test (50 held-out queries) (local/2)
