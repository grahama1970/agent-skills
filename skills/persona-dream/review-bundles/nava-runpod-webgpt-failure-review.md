# NAVA Runpod Failure Review Request

## Objective

We need a reliable first NAVA smoke for the persona-dream bakeoff. Initial comparison is NAVA joint audio-video vs Kling 3 Omni native AV. The smoke target is intentionally tiny: prove that NAVA can run its single-GPU FP8 path and emit a small reviewable MP4/WAV/manifest artifact before attempting any real Horus/Embry clip.

## Current Repo Context

Local NAVA repo:

`/home/graham/workspace/experiments/NAVA`

Important local findings:

- `README.md` says main CLI scripts are 8-GPU sequence-parallel oriented, with `flash-attn --no-build-isolation` required.
- `comfyui_nava/README.md` says the practical single-GPU route is the FP8 ComfyUI path: "Single-GPU audio-video generation" with FP8 around 18 GB VRAM.
- `comfyui_nava/engine.py` explicitly says: "No torchrun / distributed required; runs in-process inside ComfyUI."
- `nava_src/models/nava/modules/attention.py` asserts `FLASH_ATTN_2_AVAILABLE` at the main flash attention path. A hand-written SDPA fallback was attempted earlier and removed because it was not repo-sanctioned.

## Current Launcher

Launcher under review:

`/home/graham/workspace/experiments/agent-skills/skills/persona-dream/research/bakeoff/scripts/runpod_nava_pod_smoke.py`

Current intended remote path:

1. Create capped Runpod Pod through Pod API, not Flash.
2. Use `runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04`.
3. Install dependencies.
4. Install/import `flash-attn`.
5. Import `comfyui_nava.engine.NAVAComfyEngine`.
6. Generate a tiny sample with `latent_frames=2`, `height=144`, `width=256`, `steps=2`.
7. Save:
   - `nava_comfy_smoke_video_only.mp4`
   - `nava_comfy_smoke_audio.wav`
   - `nava_comfy_smoke_muxed.mp4`
   - `nava_comfy_smoke_manifest.json`
8. Download outputs.
9. Always terminate the pod.

## Runpod Safety Evidence

Current external Runpod check after interrupt:

```json
{
  "pod_count": 0,
  "pods": []
}
```

Recent terminated pod receipts:

- `/tmp/persona-dream-runmode-nava/nava_lane/runpod_pod_smoke_receipt.json`
- `/tmp/persona-dream-runmode-nava/nava_lane/outputs/runpod_pod/nava_smoke.log`

## Failure History

### Failure 1: Runpod Flash timeout

Runpod Flash accepted a job, but the probe timed out. We concluded Flash is not the main full-render path for NAVA because NAVA has large checkpoints, CUDA/FlashAttention dependencies, and cold-start pressure.

### Failure 2: CLI path hit distributed sampler and FlashAttention

Original remote path used `python inference_nava.py ...` on one GPU. That was wrong for NAVA:

- CLI examples are largely 8-GPU/SP.
- Single-process CLI hit `DistributedSampler` when not DDP.
- After a sampler patch, it hit `attention.py` assertion because `flash_attn` was missing.

### Failure 3: FlashAttention build too broad

On secure A40 48GB at `$0.44/hr`, `flash-attn` compiled for multiple architectures:

```text
sm80, sm90, sm100, sm120
```

This was stopped to avoid wasting paid runtime. Launcher was patched to set:

```bash
TORCH_CUDA_ARCH_LIST=8.0
```

### Failure 4: FlashAttention import ABI mismatch with Runpod dev torch

Using `python -m venv --system-site-packages` exposed the base image torch:

```json
{
  "cuda": true,
  "gpu": "NVIDIA A40",
  "torch": "2.8.0.dev20250319+cu128"
}
```

`flash-attn` built successfully, but import failed:

```text
ImportError: /workspace/NAVA/.venv/lib/python3.11/site-packages/flash_attn_2_cuda.cpython-311-x86_64-linux-gnu.so:
undefined symbol: _ZN3c104cuda9SetDeviceEab
```

This looks like a torch/flash-attn ABI mismatch caused by the Runpod image's dev torch build.

### Current Patch Before Escalation

Launcher was patched to use an isolated venv and pin official PyTorch:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
python -m pip install packaging ninja
python -m pip install \
  torch==2.8.0+cu128 \
  torchvision==0.23.0+cu128 \
  torchaudio==2.8.0+cu128 \
  --index-url https://download.pytorch.org/whl/cu128
```

Then install normal deps and `flash-attn --no-build-isolation`.

The next paid run was interrupted so WebGPT could review before another loop. No final evidence yet that this pinned torch path fixes FlashAttention import.

## What I Need From WebGPT

Please review this as a debugging advisor. Do not give generic NAVA background.

Answer these concrete questions:

1. Is the next best step to continue with the pinned official `torch==2.8.0+cu128` isolated venv, or should we use a different torch/CUDA/FlashAttention combination?
2. Should the Runpod base image be changed to a stable PyTorch/CUDA image that is known compatible with FlashAttention, instead of `runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04`?
3. Should we avoid building FlashAttention from source and install a specific prebuilt wheel? If yes, provide the exact selection logic or example URL pattern for Python 3.11, CUDA 12.x, torch 2.8 or another recommended torch.
4. Is `TORCH_CUDA_ARCH_LIST=8.0` sufficient for A40, or should it be `8.0;8.6` or another value?
5. Is direct use of `comfyui_nava.engine.NAVAComfyEngine` a valid standalone path, or should the smoke instead use the shipped ComfyUI node workflow / Gradio engine?
6. What exact minimal remote script should be run next to prove environment readiness before downloading full NAVA weights?
7. Given repeated failure, what should be the stop condition before another paid full attempt?

Preferred answer format:

```text
Verdict:
Recommended runtime stack:
Minimal environment probe:
Minimal NAVA smoke:
Specific changes to runpod_nava_pod_smoke.py:
Stop conditions:
```
