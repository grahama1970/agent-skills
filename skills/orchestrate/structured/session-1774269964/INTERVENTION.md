# Intervention Controls

Session: session-1774269964

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Research RunPod Flash SDK capabilities for training workloads (subagent-service/0)
- `2`: Create common/flash_trainer.py adapter (subagent-service/0)
- `3`: Add runpod to create-gpt pyproject.toml + --target flag (subagent-service/1)
- `4`: Add --target flag to classifier-lab (subagent-service/1)
- `5`: Wire assistant-lab train-remote to use Flash instead of ops-runpod (subagent-service/1)
- `6`: Integration test: dry-run Flash training for 0.5B model (local/2)
- `7`: Update SKILL.md docs for all modified skills (subagent-service/2)
