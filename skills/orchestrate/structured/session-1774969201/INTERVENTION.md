# Intervention Controls

Session: session-1774969201

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `A1-ingest-code-treesitter`: Enhance ingest-code rescan to extract symbols via treesitter (code-runner/track-a)
- `A2-embedding-verification`: Add --verify-embeddings flag to ingest-code rescan (code-runner/track-a)
- `A3-monitor-codebase-step6`: Update monitor-codebase Step 6 to use --treesitter flag (code-runner/track-a)
- `B1-replace-subagent-dispatch`: Replace Step 10 broken subagent dispatch with orchestrate code-runner (code-runner/track-b)
- `C1-trend-comparison`: Add trend comparison step: diff current report vs previous (code-runner/track-c)
- `C2-trend-to-memory`: Create trend_tracker.py to store trend data to memory (code-runner/track-c)
- `D1-cleanup-skill-md`: Remove dead composes and update SKILL.md pipeline table (code-runner/track-d)
