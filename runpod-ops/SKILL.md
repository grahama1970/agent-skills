---
name: runpod-ops
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
  project-path: /home/graham/workspace/experiments/runpod_ops
---

# RunPod Operations Skill

Manage RunPod GPU instances for LLM training and inference.

**Self-contained skill** - auto-installs via `uv run` from git (no pre-installation needed).

## Quick Start

```bash
# Via wrapper (recommended - auto-installs)
.agents/skills/runpod-ops/run.sh list-instances

# List running instances
./run.sh list-instances

# Create an instance
./run.sh create-instance 70B --hours 4

# Monitor an instance
./run.sh monitor <pod-id>

# Terminate an instance
./run.sh terminate <pod-id>
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
```bash
runpod_ops create-instance 70B --hours 4
# Returns: pod_id=abc123
```

### Estimate Cost
```bash
runpod_ops estimate-cost 70B --hours 8
```

### Monitor Instance
```bash
runpod_ops monitor <pod-id>
```

### Terminate Instance
```bash
runpod_ops terminate <pod-id>
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `RUNPOD_API_KEY` | Yes | RunPod API key |

## Typical Workflow

```bash
# 1. Estimate cost
runpod_ops estimate-cost 70B --hours 8

# 2. Create pod
runpod_ops create-instance 70B --hours 8

# 3. Monitor or SSH into pod
runpod_ops monitor <pod-id>

# 4. Run training...

# 5. Terminate when done
runpod_ops terminate <pod-id>
```

## Integration with Memory

After training completes, log the lesson:
```bash
memory-agent learn \
  --problem "Training Qwen3-70B on RunPod" \
  --solution "Used A100-80GB, 8 hours, cost $24.72. Config: lr=2e-5, batch=4"
```
