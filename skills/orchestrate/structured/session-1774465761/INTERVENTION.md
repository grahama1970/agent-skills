# Intervention Controls

Session: session-1774465761

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `T1`: Serve worksheets.yaml via Express API (subagent-service/ws1)
- `T2`: Create useWorksheets hook (subagent-service/ws1)
- `T3`: Refactor SourcesView to use useWorksheets (subagent-service/ws1)
- `T4`: Add SpartaNavContext for cross-tab navigation (subagent-service/ws2)
- `T5`: Replace inline QRAs in SourcesView with cross-tab link (subagent-service/ws2)
- `T6`: QRAsView accepts filter from navigation (subagent-service/ws2)
- `T7`: Update /extract-entities skill with delimiter support (subagent-service/ws3)
- `T8`: Wire ControlIdPills to use delimiter mode (subagent-service/ws3)
- `T9`: SourcesView flyout + UtilityBar + Toast (subagent-service/ws4)
- `T10`: Magnetic hover + status badges for SourcesView (subagent-service/ws4)
- `T11`: Full verification + blind testing (subagent-service/ws4)
