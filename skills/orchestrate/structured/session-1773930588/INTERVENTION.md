# Intervention Controls

Session: session-1773930588

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Create ground truth fixture from droid binary (subagent-service/0)
- `2`: Design classification prompt via /prompt-lab (subagent-service/0)
- `3`: Design AST classification prompt via /prompt-lab (subagent-service/0)
- `4`: Rewrite classifier.py to load prompts from references/ (subagent-service/1)
- `5`: Wire /treesitter AST into the pipeline (subagent-service/1)
- `6`: Wire --help parsing + subcommand discovery (subagent-service/1)
- `7`: Register analyze-elf classifiers in /assistant model_registry (subagent-service/2)
- `8`: Wire CascadeRunner into classifier.py (subagent-service/2)
- `9`: Prime shadow data from droid binary (local/2)
- `10`: Auto-generate /create-walkthrough prosecution brief (subagent-service/3)
- `11`: End-to-end validation + skills-ci (local/3)
- `12`: Learn to /memory (local/3)
