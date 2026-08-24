---
name: ops-chutes
description: >
  Manage Chutes.ai resources, tracking subscription quota and account balance.
  Integrates with scheduler to pause operations when quota is reached.
triggers:
  - check chutes
  - chutes usage
  - chutes budget
  - chutes status
  - chutes models
  - list chutes models
  - what models are on chutes
  - chutes model list
  - is model X ready?
  - wait for chutes reset
  - can I run X calls?
  - check chutes health
  - chutes api check
  - is chutes slow
  - chutes overloaded
  - switch from TEE
  - recommend non-TEE
  - TEE vs non-TEE
metadata:
  short-description: Chutes.ai API management and Quota tracking

provides:
  - ops-chutes
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - observability-operations
  - model-ops
---

# Ops Chutes Skill

Manage Chutes.ai resources and monitor subscription quota and account balance.

## Triggers

- "Check chutes status" -> `status`
- "How much chutes budget left?" -> `usage`
- "Is chutes working?" -> `sanity [model]`

## Commands

```bash
# Check model status (hot/cold/down)
./run.sh status

# Check Subscription Quota and Remaining Balance
./run.sh usage [--chute-id <id>] [--json]

# Explore all available models (filterable)
# Flags: --query (name), --owner (sglang/vllm), --modality (text/image), --feature (reasoning/tools), --json
./run.sh models [--query <search>] [--owner <owner>] [--modality <modality>] [--feature <feature>] [--json]

# Check model health (HOT/COLD/DOWN)
./run.sh model-health <model_id>

# Rank all variants in a model family by speed, recommend the best
# Finds TEE + non-TEE siblings, pings each, shows ranked table
./run.sh recommend <model_id>          # e.g. deepseek-ai/DeepSeek-V3.1-TEE
./run.sh recommend <model_id> --json   # JSON output for automation
./run.sh recommend <model_id> --skip-ping  # Metadata only, no latency test

# Run sanity check (Inference via Qwen/Qwen2.5-72B-Instruct)
./run.sh sanity [model_name]

# Check budget (exit 1 if Quota exhausted OR Balance < CHUTES_MIN_BALANCE)
./run.sh budget-check

# Wait until quota resets (7PM ET)
./run.sh wait-for-reset [--timeout <seconds>]

# Verify if a batch of calls is feasible (exit 1 if not)
./run.sh can-complete <num_calls>
```

## Environment Variables

| Variable             | Description                               |
| -------------------- | ----------------------------------------- |
| `CHUTES_API_TOKEN`   | API Token (standard)                      |
| `CHUTES_API_KEY`     | API Key (alternative naming)              |
| `CHUTES_MIN_BALANCE` | Minimum balance threshold (default: 0.05) |

## TEE vs Non-TEE Model Selection

Chutes.ai miners generally prefer non-TEE models because:
- **Higher throughput**: TEE enclave overhead reduces TPS by ~10-20%
- **More miners serving**: Non-TEE models get higher utilization and more active nodes
- **Faster cold starts**: No enclave initialization delay

Use `recommend` to find the fastest variant. TEE is only needed when data privacy/isolation
is a legal or compliance requirement.

## Usage Reports & Analytics

```bash
# Daily usage (last 30 days, default)
./run.sh report

# Monthly aggregation (all-time)
./run.sh report --monthly

# Show only days that exceeded the 5K quota
./run.sh report --spikes

# Hourly breakdown for a specific date
./run.sh report --hourly 2026-02-18

# JSON output for automation / /create-figure
./run.sh report --monthly --json
./run.sh report --spikes --json
./run.sh report --hourly 2026-02-18 --json

# Last 7 days only
./run.sh report --days 7
```

Data source: `/users/me/usage` API (hourly granular buckets with token counts and costs).

## Concurrency Throttle

Cross-process semaphore enforcing the 5-slot Chutes.ai concurrency limit.
Uses `fcntl.flock()` on 5 slot files — lock auto-releases on process crash.

```bash
# Acquire a slot (blocks until available, 90s timeout)
./run.sh acquire [--timeout 90]

# Show slot usage
./run.sh slots

# Python context manager
from throttle import ChutesSemaphore
with ChutesSemaphore() as slot:
    print(f"Using slot {slot}")
    # ... make Chutes API calls ...
```

Slot files: `~/.pi/ops-chutes/semaphore/slot_{0..4}`

> [!WARNING]
> **Concurrency Limit**: Chutes.ai allows **5 concurrent connections** per token.
> The throttle enforces this via OS-level file locks. Exceeding the limit returns
> a 429 Rate Limit error with a **90-second pause**.

## Common Mistakes

### WRONG: Using TEE model variants for batch work
```python
model = "deepseek-ai/DeepSeek-V3.1-TEE"  # 4x slower, 429s at high load
```

### RIGHT: Use non-TEE variants for batch operations
```bash
./run.sh recommend deepseek-ai/DeepSeek-V3.1-TEE  # shows fastest variant
# Use the recommended non-TEE model
```

### WRONG: Launching batch jobs without checking budget first
```bash
./run.sh  # starts burning tokens without checking quota
```

### RIGHT: Budget-check before batch operations
```bash
./run.sh budget-check  # exits 1 if quota exhausted or balance low
./run.sh can-complete 500  # verify 500 calls are feasible
```

### WRONG: Exceeding 5 concurrent connections across processes
```python
# Multiple processes each opening 6 async connections = self-DoS
```

### RIGHT: Use the ChutesSemaphore for cross-process coordination
```python
from throttle import ChutesSemaphore
with ChutesSemaphore() as slot:
    # make Chutes API calls safely
    pass
```

## References (retrieve on demand — do not vendor)

External docs drift; cite the canonical URLs and fetch them when needed
with `/context7` (library docs) or `/fetcher` (any URL/PDF) rather than
caching stale copies. Verified reachable (HTTP 200) 2026-08-24.

- Chutes.ai documentation: <https://docs.chutes.ai/>
- llms.txt (LLM-friendly doc index): <https://chutes.ai/llms.txt>

```bash
skills/context7/run.sh "chutes.ai api quota"
skills/fetcher/run.sh "https://docs.chutes.ai/"
```
