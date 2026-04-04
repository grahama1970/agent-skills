# Intervention Controls

Session: session-1775131363

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Add skill discovery to plan.py task decomposition (code-runner/0)
- `2`: Upgrade review-plan check_skill_overlap to use manifest + recommend-skill-chain (code-runner/1)
- `3`: Update /plan SKILL.md runner table to show code-runner as default (code-runner/2)
- `4`: Validate end-to-end: plan.py emits skills, review-plan checks them (local/2)
