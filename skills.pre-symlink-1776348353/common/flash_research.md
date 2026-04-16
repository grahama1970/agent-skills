# RunPod Flash SDK — Research Findings

**Researched**: 2026-03-23
**runpod package version**: 1.8.1 (verified: `pip install runpod && python3 -c 'import runpod; print(runpod.__version__)'`)
**runpod-flash package**: separate install via `pip install runpod-flash`

---

## 1. Flash SDK Overview

RunPod **Flash** is a Python SDK for running GPU workloads on RunPod Serverless **without Docker**. Developers write local Python functions, decorate them with `@Endpoint`, and Flash handles provisioning, dependency installation, and autoscaling automatically. Docker still runs under the hood on the remote worker, but you never author a Dockerfile.

- **Repo**: https://github.com/runpod/flash
- **Docs**: https://docs.runpod.io/flash/quickstart
- **PyPI**: `pip install runpod-flash`
- **Python requirement**: 3.10–3.12 (3.13+ not supported); GPU workers use Python 3.12 only
- **Platforms**: macOS and Linux (Windows in development)

### Basic Usage

```python
from flash import Endpoint, GpuType

@Endpoint(
    name="my-training-job",
    gpu=GpuType.NVIDIA_A100_80GB_PCIe,
    workers=[1, 3],
    dependencies=["torch", "transformers"],
)
async def train(params: dict) -> dict:
    import torch
    # training logic here
    return {"status": "done"}
```

> **Note**: Dependencies must be imported *inside* the function body, not at module level.

---

## 2. Max Execution Time — **7 Days Confirmed**

| Setting | Default | Range |
|---|---|---|
| **Execution Timeout** | 600 s (10 min) | **5 s → 7 days** |
| **Job TTL (Time-to-Live)** | 24 hours | 10 s → 7 days |

- **Execution Timeout**: Maximum wall-clock duration for a single job. When exceeded, the job fails and the worker stops. Configurable in Advanced endpoint settings or per-request via `executionTimeout` in the job policy.
- **Job TTL**: Total lifespan of a job in the system (includes queue time). Job data is deleted after TTL regardless of state. The timer starts at *submission*, not execution — budget queue wait time accordingly.
- For training workloads, set both to 7 days and implement checkpoint-based recovery to handle any unexpected interruptions.

---

## 3. Storage Options

### 3a. Ephemeral Container Storage
- Each pod/worker has a local container disk that is **wiped** when the pod terminates.
- **Do not** rely on this for training checkpoints or datasets across sessions.

### 3b. Network Volumes (Persistent)
- External NVMe SSD volumes that survive pod termination.
- Mount point in Serverless workers: **`/runpod-volume`**
- Mount point in Instant Clusters (training): **`/workspace`**
- Transfer speeds: **200–400 MB/s** sustained, up to **10 GB/s** peak
- Capacity: up to 4 TB standard; larger sizes available via support
- **Volumes can be expanded but never reduced**
- **Concurrent writes from multiple workers can cause data corruption** — implement locking in application logic

**Storage pricing:**

| Tier | Price |
|---|---|
| First 1 TB | $0.07 / GB / month |
| Beyond 1 TB | $0.05 / GB / month |

### 3c. S3-Compatible Object Storage
- RunPod exposes an S3-compatible API for large datasets and artifacts.
- Usable with `boto3`, `s3transfer`, or `runpodctl` for cross-volume synchronization.
- Suitable for dataset ingestion and model artifact export.

### 3d. Storage Strategy for Training
- Keep datasets and base model weights on a Network Volume to eliminate re-download cold starts.
- Write checkpoints to `/runpod-volume` every N steps (e.g., every 5–10 minutes).
- On job restart, scan for the latest checkpoint and resume.
- For multi-datacenter resilience, attach multiple volumes from different regions and synchronize with the S3-compatible API.

---

## 4. GPU Types Available

### Flash SDK `GpuType` Enum (direct Flash SDK)
| Enum | GPU | VRAM |
|---|---|---|
| `GpuType.NVIDIA_GEFORCE_RTX_4090` | RTX 4090 | 24 GB |
| `GpuType.NVIDIA_RTX_6000_ADA_GENERATION` | RTX 6000 Ada | 48 GB |
| `GpuType.NVIDIA_A100_80GB_PCIe` | A100 PCIe | 80 GB |

### Broader RunPod Platform GPU Groups
| Group | GPUs Included |
|---|---|
| `ADA_24` | L4, RTX 4000 series (24 GB) |
| `ADA_32_PRO` | Professional Ada 32 GB |
| `ADA_48_PRO` | L40, L40S, RTX 6000 Ada (48 GB) |
| `ADA_80_PRO` | High-end Ada 80 GB |
| `AMPERE_16` | RTX 3060, A2000, A4000 |
| `AMPERE_24` | RTX 3070/3080/3090, A4500, A5000 |
| `AMPERE_48` | A40, RTX A6000 |

### High-End / Enterprise GPUs
- NVIDIA H100 (SXM and PCIe) — 80 GB
- NVIDIA H200 SXM — 141 GB
- NVIDIA B200 — 180 GB
- NVIDIA RTX 5090 — 32 GB
- AMD MI300X — 192 GB

### Multi-GPU Serverless Support
- Serverless endpoints support **multi-GPU assignments** (e.g., 2× 80 GB A100, or up to 10× 24 GB GPUs per job).
- Instant Clusters support distributed training across nodes with shared Network Volumes.

---

## 5. Data Upload Mechanism

| Method | Use Case |
|---|---|
| **Network Volume pre-load** | Upload dataset to a volume once; attach to all workers |
| **S3-compatible API** | Programmatic upload/download via `boto3` or CLI |
| **`runpodctl`** | CLI tool for volume-to-volume sync and data transfer |
| **In-function download** | Download from HuggingFace / S3 inside the remote function (slower cold start) |
| **FlashBoot cache** | Retains worker state after spin-down for faster revival |

**Recommended for training**:
1. Pre-upload dataset to a Network Volume via S3 API or runpodctl.
2. Attach the volume to the endpoint → workers see data at `/runpod-volume` on startup.
3. Eliminates per-job re-download costs and dramatically reduces cold start time.

---

## 6. Worker Scaling Configuration

| Setting | Default | Notes |
|---|---|---|
| Active (warm) workers | 0 | Keep > 0 to eliminate cold starts |
| Max workers | 3 | Concurrency cap; raise for parallel training jobs |
| GPUs per worker | 1 | Increase for multi-GPU training |
| Idle timeout | 5 s | Time before idle worker shuts down |
| FlashBoot | Enabled | Retains worker state across spin-down cycles |

---

## 7. Pricing Reference (GPU Compute)

| GPU | On-Demand Price |
|---|---|
| A100 (80 GB) | ~$1.64/hr (Community Cloud) |
| H100 SXM | market rate |
| AWS p4d equivalent | ~$3.67/hr+ |

RunPod Community Cloud is significantly cheaper than AWS for equivalent GPU access.

---

## 8. Limitations & Gotchas

1. **No native checkpoint API in Flash SDK** — implement checkpointing in your training script using PyTorch/HF callbacks writing to `/runpod-volume`.
2. **Datacenter lock-in**: A single attached Network Volume constrains workers to that datacenter, limiting GPU availability. Mitigate with multi-datacenter volumes.
3. **Python 3.12 only on GPU workers** — ensure your training code is 3.12 compatible.
4. **Job TTL starts at submission** — if the queue is backed up, execution time budget shrinks. For 7-day training runs, set TTL to maximum (7 days) and ensure the job starts quickly.
5. **Concurrent writes to shared volumes risk data corruption** — use a single writer pattern or implement distributed checkpoint locking (e.g., file-lock or a coordinator process).
6. **Flash is in beta** — community support via Discord; production training should also evaluate the standard `runpod` SDK with custom Docker workers for more control.

---

## 9. Relevant Documentation Links

- Flash Quickstart: https://docs.runpod.io/flash/quickstart
- Flash Blog Post: https://www.runpod.io/blog/introducing-flash-run-gpu-workloads-on-runpod-serverless-no-docker-required
- Network Volumes: https://docs.runpod.io/storage/network-volumes
- Endpoint Configuration: https://docs.runpod.io/serverless/endpoints/endpoint-configurations
- GitHub Flash: https://github.com/runpod/flash
- GitHub Flash Examples: https://github.com/runpod/flash-examples
- PyPI runpod-flash: https://pypi.org/project/runpod-flash/
