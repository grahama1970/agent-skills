# Intervention Controls

Session: session-1774102636

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `T1`: Implement /consume-midi search + ingest (subagent-service/0)
- `T2`: Implement /create-midi compose + move midi_utils.py (subagent-service/0)
- `T3`: Implement /story-lab converge.py (subagent-service/0)
- `T4`: Rewrite pipeline.py for 10-stage architecture (subagent-service/1)
- `T5`: Build S03 stem viewer React component from Stitch mockup (subagent-service/2)
- `T6`: Build S04 lyrics editor React component from Stitch mockup (subagent-service/2)
- `T7`: Build pipeline view + remaining stage components (subagent-service/2)
- `T8`: Create /prompt-lab prompts for S04 annotation + S05 composition + S06 compile (subagent-service/1)
- `T9`: End-to-end dry-run: Whisperheads (subagent-service/3)
