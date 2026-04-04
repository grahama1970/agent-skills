# Intervention Controls

Session: session-1775152773

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `0.1`: Generate embeddings for app_actions collection (dense=0.00 → 384d) (local/0)
- `0.2`: Generate datalake-explorer training data from app_actions (129 actions → NL variations) (code-runner/0)
- `0.3`: Verify app_actions populated on Datalake Explorer load (129 actions registered) (local/0)
- `1.1`: Build Tier 0 deterministic action resolver (BM25 + FlashText + fuzzy match) (code-runner/1)
- `1.2`: Add /api/queryspec/resolve endpoint to UX Lab server (code-runner/1)
- `1.3`: Build Tier 0 eval harness — measure BM25 resolver accuracy on 50 hand-labeled examples (code-runner/1)
- `2.1`: Run training data generator to produce ~1500 datalake action training examples (local/2)
- `2.2`: Validate system prompt via /prompt-lab before any model training (code-runner/2)
- `2.3`: Zero-shot model comparison: qwen2.5-7b vs qwen2.5-3b vs deepseek-r1-7b on UI_COMMAND (code-runner/2)
- `3.1`: Split training data into train/eval and convert to SFT chat format (local/3)
- `3.2`: SFT warmup training on datalake UI_COMMAND data (local/3)
- `3.3`: Evaluate fine-tuned model on holdout set — target 80% action accuracy (local/3)
- `3.4`: Register datalake-intent model in model_registry.json (scillm/3)
- `4.1`: Wire ChatFAB sendMessage to query /api/queryspec/resolve BEFORE /memory intent (code-runner/4)
- `4.2`: Add training pair storage — every successful execution → /memory learn (code-runner/4)
- `5.1`: E2E test: surf CDP → type NL command → verify DOM click → screenshot evidence (local/5)
- `5.2`: Build /test-interactions manifest for QuerySpec E2E (20 action tests) (code-runner/5)
- `5.3`: Register resolver as cascade decision point in /assistant model_registry (scillm/5)
- `5.4`: Run Tier 0 eval harness and report baseline accuracy (local/5)
