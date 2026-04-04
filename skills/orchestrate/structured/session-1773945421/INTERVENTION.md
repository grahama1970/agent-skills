# Intervention Controls

Session: session-1773945421

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Add first-attempt-only eval mode to pl_eval.py (subagent-service/0)
- `2`: Add failure compilation to pl_optimize.py (subagent-service/0)
- `2.5`: Remove call_llm_with_correction from llm.py (subagent-service/0)
- `3`: Rebuild optimize command as iterative prompt rewriter with judge model (subagent-service/0)
- `4`: Add optimize-live server endpoint (subagent-service/1)
- `4.5`: Design board for prompt evolution Live tab (subagent-service/2)
- `5`: Redesign Live tab for prompt evolution view (subagent-service/2)
- `6`: End-to-end test: agent-driven optimize loop via WebSocket (subagent-service/3)
