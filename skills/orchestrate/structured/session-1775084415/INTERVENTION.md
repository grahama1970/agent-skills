# Intervention Controls

Session: session-1775084415

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Replace codex exec in hack chaos.py with scillm API (code-runner/0)
- `2`: Remove codex exec from create-icon creator.py (flip scillm to primary) (code-runner/0)
- `3`: Create hack exploit_writer.py — code-runner wrapper for exploit generation (code-runner/1)
- `4`: Create battle patch_writer.py — code-runner wrapper for patch generation (code-runner/1)
- `5`: Wire exploit_writer into hack commands.py exploit command (code-runner/2)
- `6`: Wire exploit_writer into battle red_team.py attack_phase (code-runner/2)
- `7`: Wire patch_writer into battle blue_team.py defend_phase (code-runner/2)
- `8`: Update SKILL.md and config for both skills (code-runner/2)
- `9`: Compile check all modified files (local/3)
- `10`: Run hack sanity.sh (local/3)
- `11`: Run battle sanity.sh (local/3)
- `12`: Run skills-ci scan for hack and battle (local/3)
