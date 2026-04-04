# Intervention Controls

Session: session-1775064587

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Fix MessageItem rendering order: reasoning → evidence → answer → cards (subagent-service/0)
- `2`: Add nested children to ReasoningStep type and ReasoningChain component (subagent-service/0)
- `3`: Add answer separator and 'Thinking' label to ReasoningChain header (subagent-service/0)
- `4`: Add inline interactive artifact rendering + right-pane expand (subagent-service/0)
- `5`: Add WebSocket activity channel to embry-terminal server (subagent-service/1)
- `6`: Add suggestion accept/reject REST endpoints (subagent-service/1)
- `7`: Add optional Slack/Teams webhook integration (subagent-service/1)
- `8`: Create useActivityFeed hook in shared-chat (subagent-service/2)
- `9`: Create ActivityFeed component in shared-chat (subagent-service/2)
- `10`: Create PresenceBar component in shared-chat (subagent-service/2)
- `11`: Create SuggestionCard component in shared-chat (subagent-service/2)
- `12`: Wire activity feed + presence + suggestions into EmbryTerminalView (subagent-service/3)
- `13`: Wire activity feed into SPARTA Explorer ChatTab (subagent-service/3)
- `14`: Start dev server and verify rendering (local/4)
- `15`: Visual verification — reasoning + artifacts + activity + presence (subagent-service/4)
- `16`: Brandon Bailey persona review — reasoning + artifacts + collaboration (subagent-service/4)
