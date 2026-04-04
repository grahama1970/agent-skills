# Intervention Controls

Session: session-1774373840

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Install react-force-graph-2d and migrate BinaryGraph to WebGL (subagent-service/0)
- `2`: Wire /extract-entities as Express API endpoint (subagent-service/0)
- `3`: Implement exploration step recording (Investigation Journal) (subagent-service/1)
- `4`: Wire InvestigationJournal into BinaryExplorerView (subagent-service/1)
- `5`: Implement undo/redo stack for scene operations (subagent-service/2)
- `6`: Gemini visual polish: edge thickness, arrowheads, node rendering (subagent-service/2)
- `7`: Run 144 tests from Testing tab with visual_assert verification (subagent-service/3)
- `8`: Add investigation journal tests to manifest (subagent-service/3)
