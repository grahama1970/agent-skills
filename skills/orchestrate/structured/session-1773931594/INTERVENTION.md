# Intervention Controls

Session: session-1773931594

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `T1`: Music Lab TypeScript types + sample data (subagent-service/0)
- `T2`: PianoRollView component (subagent-service/1)
- `T3`: WaveformView component (subagent-service/1)
- `T4`: ConvergenceChart component (subagent-service/1)
- `T5`: LyricsEditor component (subagent-service/1)
- `T6`: MusicLabWorkbench dashboard + App.tsx integration (subagent-service/2)
- `T7`: Design review of music-lab components (subagent-service/3)
