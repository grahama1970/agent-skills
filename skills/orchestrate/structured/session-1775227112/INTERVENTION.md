# Intervention Controls

Session: session-1775227112

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `0`: Pre-flight: verify Express + Vite + memory daemon are running (local/0)
- `1`: Express endpoints: all /api/posture/* routes (frameworks, families, gaps, risks, alerts, overview) (code-runner/0)
- `2`: Restart Express server and verify all posture endpoints return real data (local/0)
- `5`: Update usePostureData hook to use dedicated /api/posture/* endpoints (code-runner/1)
- `6`: Implement PostureDashboard.tsx — full 3ft compliance view from V1 mockup (code-runner/1)
- `7`: Implement OverviewLanding.tsx — 5ft landing page with 4 live content wells (code-runner/1)
- `8`: Add Gauge icon to nav strip + wire Posture tab in SpartaExplorer (code-runner/2)
- `9`: Family flyout panel — drill into controls for selected family (code-runner/2)
- `10`: Generate CDP live DOM interaction manifest for PostureDashboard (local/3)
- `11`: CDP live DOM test manifest — generate and validate from running browser (code-runner/3)
- `12`: VLM review — compare implementation screenshots to approved V1 mockup (code-runner/3)
