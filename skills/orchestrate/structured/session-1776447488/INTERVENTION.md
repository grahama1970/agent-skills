# Intervention Controls

Session: session-1776447488

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Run baseline extraction and write a visible audit report (local/0)
- `2`: Fix TOC range handling and tabular extraction regressions in the PDF Lab extractor (code-runner/1)
- `3`: Re-run the final visible audit and publish the outcome (local/2)
