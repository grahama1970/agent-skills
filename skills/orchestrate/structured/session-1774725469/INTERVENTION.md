# Intervention Controls

Session: session-1774725469

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Install polars + accelerate in classifier-lab venv (local/0)
- `2`: Pin transformers<5 in classifier-lab pyproject.toml (subagent-service/0)
- `3`: backbone_train_loop.py: output confusion matrix + per-class metrics (subagent-service/1)
- `4`: concurrent_run.py: write ALL project files matching tab contracts (subagent-service/1)
- `5`: Save dataset as Parquet with polars (text + vision) (subagent-service/1)
- `6`: Server: implement tune-results endpoint (subagent-service/2)
- `7`: Server: implement eval-results endpoint (subagent-service/2)
- `8`: Server: implement gpu-info endpoint (subagent-service/2)
- `9`: Server: implement rerun endpoint (POST submits Switchboard manifest) (subagent-service/2)
- `10`: Fix EvaluateTab to render real confusion matrix + per-class metrics (subagent-service/3)
- `11`: Fix TuneTab to render real round/trial data (subagent-service/3)
- `12`: Fix PromoteTab to show real export + deployment status (subagent-service/3)
- `13`: Fix BenchmarkTab parallel coordinates to use real data (subagent-service/3)
- `14`: Add RERUN button component (shared across tabs) (subagent-service/4)
- `15`: Add edit controls to Train tab (backbone list, gate threshold, max rounds) (subagent-service/4)
- `16`: Add edit controls to Research tab (rerun dogpile) (subagent-service/4)
- `17`: Run full concurrent training and verify ALL tabs show real data (local/5)
- `18`: Verify UI tabs render correctly via headless screenshot (local/5)
