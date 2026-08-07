---
name: ops-runpod
description: >
  Provision, manage, and terminate RunPod GPU instances for LLM training. Use when
  user says "spin up GPU", "create RunPod instance", "terminate pod", "check GPU status",
  "provision training server", or needs cloud GPU resources.
allowed-tools: Bash, Read
triggers:
  - spin up GPU
  - create RunPod
  - terminate pod
  - GPU instance
  - provision server
  - check pod status
  - RunPod management
metadata:
  short-description: RunPod GPU instance management
  project-path: $RUNPOD_OPS_REPO (set via env; defaults to GitHub clone)

provides:
  - ops-runpod
composes: [task-monitor]
disciplines:
  - model-ops
  - observability-operations
---

# RunPod Operations Skill

Manage RunPod GPU instances for LLM training and inference.

**Self-contained skill** - auto-installs via `uv run` from git (no pre-installation needed).

## Quick Start

```bash
# Via wrapper (auto-installs from GitHub on demand)
.pi/skills/ops-runpod/run.sh list-instances

# Create an instance
.pi/skills/ops-runpod/run.sh create-instance 70B --hours 4

# Monitor an instance
.pi/skills/ops-runpod/run.sh monitor <pod-id>

# Terminate an instance
.pi/skills/ops-runpod/run.sh terminate <pod-id>
```

## Commands

| Command | Purpose |
|---------|---------|
| `create-instance` | Create GPU pod optimized for model size |
| `list-instances` | Show all running pods with status/cost |
| `monitor` | Live monitoring of pod metrics |
| `terminate` | Safely terminate a pod |
| `estimate-cost` | Estimate training cost before creating |
| `optimize` | Find optimal GPU config using benchmarks |
| `start-training` | Start a training job on RunPod |
| `serve` | Start inference server on RunPod |

## Examples

### Create Instance
.pi/skills/ops-runpod/run.sh create-instance 70B --hours 4
# Returns: pod_id=abc123
```

### Estimate Cost
```bash
.pi/skills/ops-runpod/run.sh estimate-cost 70B --hours 8
```

### Monitor Instance
```bash
.pi/skills/ops-runpod/run.sh monitor <pod-id>
```

### Terminate Instance
```bash
.pi/skills/ops-runpod/run.sh terminate <pod-id>
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `RUNPOD_API_KEY` | Yes | RunPod API key |

## Typical Workflow

```bash
# 1. Estimate cost
.pi/skills/ops-runpod/run.sh estimate-cost 70B --hours 8

# 2. Create pod
.pi/skills/ops-runpod/run.sh create-instance 70B --hours 8

# 3. Monitor or SSH into pod
.pi/skills/ops-runpod/run.sh monitor <pod-id>

# 4. Run training...

# 5. Terminate when done
.pi/skills/ops-runpod/run.sh terminate <pod-id>
```

## Deepseek V3 FP8 Deployment (Large-Scale Inference)

For deploying Deepseek V3 (671B MoE, ~350GB FP8) for large-scale QRA generation:

### Requirements

| Component | Specification |
|-----------|--------------|
| GPU | 8x A100 80GB or 8x H100 80GB |
| VRAM | 640GB total (FP8 requires ~350GB) |
| Volume | 750GB (model + cache) |
| Docker | `lmsysorg/sglang:latest` |
| Tensor Parallel | TP=8 |

### Estimate Cost (Before Deploying)

```bash
.pi/skills/ops-runpod/deploy-deepseek-v3.sh --estimate-only --hours 12
```

### Deploy for Overnight Job

```bash
# Cost-optimized (8x A100, ~$15/hr)
.pi/skills/ops-runpod/deploy-deepseek-v3.sh --hours 12

# Speed-optimized (8x H100, ~$24/hr)
.pi/skills/ops-runpod/deploy-deepseek-v3.sh --hours 8 --fast
```

### Throughput Estimates

| GPU Config | Tokens/sec | QRAs/hour (1K tokens) | 90K QRAs Time |
|------------|------------|----------------------|---------------|
| 8x A100 | ~150 | ~540 | ~12-14 hours |
| 8x H100 | ~250 | ~900 | ~7-9 hours |

### First-Time Deployment

First run requires ~45 min for model download (~350GB). Subsequent runs use cached weights.

### Cost Comparison

| Config | Hourly | 90K QRAs | Notes |
|--------|--------|----------|-------|
| 8x A100 Spot | ~$15/hr | ~$180-200 | Overnight recommended |
| 8x H100 Spot | ~$24/hr | ~$170-190 | Faster, similar total cost |

**Recommendation**: 8x A100 overnight for cost optimization (user preference).

## Integration with Memory

After training completes, log the lesson:
```bash
memory-agent learn \
  --problem "Training Qwen3-70B on RunPod" \
  --solution "Used A100-80GB, 8 hours, cost $24.72. Config: lr=2e-5, batch=4"
```

## Common Mistakes

### WRONG: Creating instances without estimating cost first
```bash
./run.sh create-instance 70B --hours 8  # could be $200+ surprise
```

### RIGHT: Always estimate before provisioning
```bash
./run.sh estimate-cost 70B --hours 8  # see cost before committing
./run.sh create-instance 70B --hours 8
```

### WRONG: Forgetting to terminate pods after training
```bash
./run.sh create-instance 70B --hours 8
# Training finishes in 4 hours, pod runs for 4 more hours at full price
```

### RIGHT: Terminate immediately after training completes
```bash
./run.sh terminate <pod-id>  # stop billing
```

### WRONG: Using ops-runpod for training when Flash is available
```bash
./run.sh create-instance 7B  # persistent pod for training, expensive
```

### RIGHT: Use classifier-lab or create-gpt --target flash for training
```bash
# Flash replaces ops-runpod for all training paths
.pi/skills/create-gpt/run.sh train --task X --target flash --gpu B200
```
