# Intervention Controls

Session: session-1774526953

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Replace memory-agent CLI subprocess with httpx Unix socket client (subagent-service/0)
- `2`: Add httpx to checkpoint pyproject.toml dependencies (local/0)
- `3`: Restructure problem field for BM25 findability (subagent-service/1)
- `4`: Add structured tags: project, date, branch (subagent-service/1)
- `5`: POST to /taxonomy/batch-tag after storing checkpoint (subagent-service/1)
- `6`: Add --skills CLI option for explicit skill chain declaration (subagent-service/2)
- `7`: Store skill chains with outcome polarity for recommendation (subagent-service/2)
- `8`: Add --grade CLI option with 5-level rubric (graph-traversable) (subagent-service/2)
- `9`: Ingest ~/.claude/ project memory files on checkpoint save (subagent-service/3)
- `10`: Add --mine-session flag to extract skill chains from conversation transcript (subagent-service/3)
- `8.5`: Git commit+push BOTH project AND skills, capture diff in solution_doc (subagent-service/2)
- `11`: Add --session-id and --episode-key for episodic archiver linkage (subagent-service/4)
- `11.5`: Auto-checkpoint via session-end hook using /subagent-service background call (subagent-service/4)
- `12`: Update recall/list/last commands to use httpx (subagent-service/0)
- `13`: Run /skills-ci scan and fix violations (subagent-service/5)
- `14`: End-to-end validation: save, recall by BM25, recall by semantic, verify taxonomy tags (subagent-service/5)
- `15`: Update SKILL.md to document v3 schema and new options (subagent-service/5)
