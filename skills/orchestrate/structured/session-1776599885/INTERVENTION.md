# Intervention Controls

Session: session-1776599885

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Create 12d_formalizability_scorer.py pipeline step (code-runner/0)
- `2`: Run formalizability backfill on all sparta_controls (local/1)
- `3`: Validate score distribution per framework (local/1)
- `4`: Update 13_lean4_verify.py to respect formalizability threshold (code-runner/2)
- `5`: Update /match-requirement to surface formalizability_score (code-runner/2)
- `6`: Update /create-evidence-case to check formalizability before lean4 (code-runner/2)
- `7`: E2E test: formalizability scoring + evidence case integration (local/3)
- `8`: Document formalizability scoring in SPARTA pipeline docs (local/3)
