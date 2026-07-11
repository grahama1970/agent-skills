# Self-Contained NAVA Runpod Debug Review

This is a self-contained review bundle. It includes the relevant facts, snippets, and logs inline. Do not assume access to any local filesystem paths.

## Goal

We need one reliable minimal NAVA smoke for a persona-dream bakeoff. The first comparison is NAVA joint audio-video against Kling 3 Omni native AV. The smoke should prove environment readiness and produce a tiny MP4/WAV/manifest before any real Horus/Embry clip is attempted.

## NAVA Repo Facts Already Verified Locally

The local NAVA repository has these relevant properties:

- The main README says NAVA requires `flash-attn --no-build-isolation`.
- The main CLI scripts are aimed at 8-GPU sequence-parallel inference.
- The ComfyUI NAVA README says the FP8 route supports single-GPU audio-video generation, including T2AV, I2AV, and timbre-controlled I2AV, around 18 GB VRAM.
- The ComfyUI engine says it runs in-process and does not require `torchrun` or distributed execution.
- The attention implementation imports `flash_attn`; the main fast path asserts FlashAttention is available.

The intended smoke was changed from the 8-GPU CLI to the ComfyUI single-GPU engine.

## Intended Runtime Shape

Use Runpod Pod API, not Runpod Flash, because NAVA is heavy and needs a real environment. Target GPU: A40 48 GB, secure cloud, around 0.44 USD/hour. Hard cap: 1 hour and 1 USD/hour.

Remote steps:

```bash
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export MAX_JOBS="${MAX_JOBS:-8}"
export TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-8.0}"

git clone https://github.com/ernie-research/NAVA.git
cd NAVA
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
python -m pip install packaging ninja
python -m pip install \
  torch==2.8.0+cu128 \
  torchvision==0.23.0+cu128 \
  torchaudio==2.8.0+cu128 \
  --index-url https://download.pytorch.org/whl/cu128
python -m pip install diffusers transformers accelerate safetensors huggingface_hub sentencepiece tokenizers scipy einops PyYAML tqdm opencv-python imageio imageio-ffmpeg pydub soundfile ftfy xfuser
python -m pip install flash-attn --no-build-isolation
```

Then import `flash_attn`, download the minimum NAVA artifacts, patch two small compatibility issues if needed, import `NAVAComfyEngine`, and generate with:

```python
frames, audio = engine.generate(
    prompt="A front-facing medium close-up of Embry in an archive graph environment. Embry says<S>I know I am software. The evidence still feels real.<E>",
    height=144,
    width=256,
    latent_frames=2,
    steps=2,
    video_cfg=3.0,
    audio_cfg=2.0,
    seed=42,
    vae_tiling=True,
    vae_tile_size=(8, 12),
    vae_tile_stride=(6, 10),
)
```

## Failures

### Failure 1: Runpod Flash timed out

Flash accepted a job but timed out. Conclusion so far: Flash is useful for tiny GPU probes, not the main NAVA render path.

### Failure 2: Single-GPU CLI path was wrong

An earlier attempt ran `inference_nava.py` directly on one GPU. It hit distributed sampler assumptions and then FlashAttention assertions. This route was abandoned because the NAVA repo provides a single-GPU FP8 ComfyUI engine.

### Failure 3: FlashAttention source build too broad

On A40 48 GB, `flash-attn` source build was compiling multiple architectures:

```text
sm80, sm90, sm100, sm120
```

This was stopped. The launcher was patched with:

```bash
TORCH_CUDA_ARCH_LIST=8.0
```

A40 is Ampere compute capability 8.0.

### Failure 4: ABI mismatch with base image dev torch

Using `python -m venv --system-site-packages` exposed the base image torch:

```json
{
  "cuda": true,
  "gpu": "NVIDIA A40",
  "torch": "2.8.0.dev20250319+cu128"
}
```

`flash-attn` built successfully but failed to import:

```text
ImportError: flash_attn_2_cuda.cpython-311-x86_64-linux-gnu.so:
undefined symbol: _ZN3c104cuda9SetDeviceEab
```

This appears to be a FlashAttention/PyTorch ABI mismatch, likely because the image has a development build of PyTorch.

### Current state before this review

The launcher was patched to use an isolated venv and official pinned torch:

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

However, the next paid run was interrupted before completion so this has not yet been proven.

## Safety Evidence

The last live pod was interrupted intentionally. The launcher receipt included:

```json
{
  "status": "interrupted",
  "pod_id": "doefcn1tjlqxog",
  "events": [
    {"event": "create_pod", "gpu": "NVIDIA A40", "hourly": 0.44},
    {"event": "pod_created", "pod_id": "doefcn1tjlqxog"},
    {"event": "ssh_connected"},
    {"event": "terminate_pod_start", "pod_id": "doefcn1tjlqxog"},
    {"event": "terminate_pod_done", "response": null}
  ],
  "error": "KeyboardInterrupt"
}
```

External Runpod API after termination:

```json
{
  "pod_count": 0,
  "pods": []
}
```

## Question For WebGPT

Please act as a debugging advisor. I need the next exact runtime fix, not generic NAVA background.

Answer:

1. Should the next attempt continue with isolated venv plus official `torch==2.8.0+cu128`, or should we pin an older official torch/CUDA combination known to work with FlashAttention?
2. Should the Runpod image be changed to avoid the dev torch base image entirely?
3. Should we install a prebuilt FlashAttention wheel instead of building from source? If yes, give exact version-selection logic for Python 3.11, Linux x86_64, CUDA 12.x, and chosen torch.
4. Is `TORCH_CUDA_ARCH_LIST=8.0` correct for A40?
5. Is direct standalone use of `comfyui_nava.engine.NAVAComfyEngine` valid, or should the smoke use ComfyUI/Gradio entrypoints?
6. What is the smallest environment probe that should run before downloading NAVA weights?
7. What stop condition should prevent another paid full attempt?

Preferred answer format:

```text
Verdict:
Recommended runtime stack:
Minimal environment probe:
Minimal NAVA smoke:
Specific launcher changes:
Stop conditions:
```
