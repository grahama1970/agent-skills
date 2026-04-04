# Intervention Controls

Session: session-1774784829

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Build T0 deterministic evidence collector (subagent-service/0)
- `2`: Build error classifier (deterministic regex, NOT LLM) (subagent-service/0)
- `3`: Add git commit/revert pattern (autoresearch style) (subagent-service/1)
- `4`: Add experiment log (results.jsonl — like autoresearch results.tsv) (subagent-service/1)
- `5`: Build strategy escalation (5-step, like classifier-lab 10-step) (subagent-service/2)
- `6`: Build /scillm structured fix prompt with full trajectory (subagent-service/2)
- `7`: Rewrite main loop with score-based keep/discard + escalation (subagent-service/2)
- `8`: Update /orchestrate to pass DoD to code-runner spec (subagent-service/3)
- `9`: Test code-runner on a real task with intentional failure (local/3)
- `10`: Run sanity.sh and verify /skills-ci passes (local/3)
