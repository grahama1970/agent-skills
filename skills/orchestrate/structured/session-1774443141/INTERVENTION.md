# Intervention Controls

Session: session-1774443141

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Install @excalidraw/excalidraw in ux-lab (local/0)
- `2`: Add /api/architecture Express endpoints to ux-lab server (subagent-service/0)
- `3`: Create ArchitectureView.tsx — main view component (subagent-service/1)
- `4`: Register Architecture in UX Lab shell + hash routing (subagent-service/1)
- `5`: Wire Save to Memory — persist Excalidraw JSON to ArangoDB (subagent-service/2)
- `6`: Wire Create Plan — generate /plan YAML from architecture diagram (subagent-service/2)
- `7`: Agent read/write API — programmatic canvas manipulation (subagent-service/2)
- `8`: Visual review — screenshot and /review-design (subagent-service/3)
- `9`: Integration test — full round-trip (local/3)
