# Intervention Controls

Session: session-1776469368

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `0.1`: Extract PostureHUD as sticky component (code-runner/0)
- `1.1`: Add fluid typography with clamp() (code-runner/1)
- `1.2`: Convert Grid to CSS auto-fit minmax (code-runner/1)
- `2.1`: Create TacticAccordion component (code-runner/2)
- `2.2`: Integrate accordion into ThreatMatrix with breakpoint switch (code-runner/2)
- `3.1`: Create TechniqueDrawer for mobile detail view (code-runner/3)
- `3.2`: Update Grid cells for progressive disclosure (code-runner/3)
- `4.1`: Add Condensed View toggle to Header (code-runner/4)
- `4.2`: Visual verification with /test-interactions (local/4)
