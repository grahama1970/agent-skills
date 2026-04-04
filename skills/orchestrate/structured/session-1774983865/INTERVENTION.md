# Intervention Controls

Session: session-1774983865

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Extract highlightEntities to shared utility (subagent-service/0)
- `2`: Extract SkillPaletteDropdown to shared component (subagent-service/0)
- `3`: Extract MarkdownRenderer to shared component (subagent-service/0)
- `4`: Unify RecallCard — single component, both interfaces (subagent-service/1)
- `5`: Unify message types — shared ChatMessage interface (subagent-service/1)
- `6`: Create shared-chat index barrel export (subagent-service/1)
- `7`: Embry Terminal — import shared components, delete duplicates (subagent-service/2)
- `8`: Embry Terminal — add ThreatMatrix rendering in chat (subagent-service/2)
- `9`: SPARTA ChatWell — add entity highlighting to messages (subagent-service/3)
- `10`: SPARTA ChatWell — add /skill-name invocation + palette (subagent-service/3)
- `11`: SPARTA ChatWell — markdown rendering for agent responses (subagent-service/3)
- `12`: SPARTA ChatTab — integrate scratch.md vision features (subagent-service/3)
- `13`: Update Brandon Bailey test manifest for shared components (subagent-service/4)
- `14`: Run VLM persona review — Brandon Bailey on converged chat (local/4)
- `15`: Verify SPARTA Explorer chat has parity (local/4)
