## Video Model Selection Guide

Choose video model based on your GPU VRAM and use case. VRAM figures include 3-5GB headroom for pipeline overhead (ComfyUI/loader/audio), batch=1, FP8/FP4 where noted.

| VRAM | Recommended Models | Best For |
|------|-------------------|----------|
| 12GB (RTX 3060/4070) | LTX-2 Distilled (2B), CogVideoX-2B | Quick iterations, pre-viz |
| 16GB (RTX 4080/A4000) | LTX-2 19B FP4 (720p, ≤10s), WAN 2.2, SVD | Medium quality production |
| 24GB (RTX 4090/A5000) | **LTX-2 19B FP8** (recommended), WAN 2.2, Mochi | High quality production |
| 40GB+ (A100/H100) | LTX-2 BF16 (43GB), Full Mochi, Open-Sora 2.0 | Maximum quality |

### Safe Defaults (RTX A5000 24GB)

```
Model: LTX-2 19B FP8
Resolution: 720p
Clip length: 10s
Batch size: 1
Seed: fixed
Audio: on
```

If runtime VRAM >22GB or instability occurs: lower resolution to 540p, disable audio, or shorten clips. Avoid parallel jobs on 24GB.

### Model Characteristics

| Model | Speed | Quality | Audio | Best Use Case |
|-------|-------|---------|-------|---------------|
| **LTX-2 19B FP8** ⭐ | Fast | High | Yes | **Recommended** - Camera controls, audio sync |
| **LTX-2 Distilled** | Fastest | Medium | Yes | Rapid iteration, light VRAM |
| **WAN 2.2 14B** | Slow | Very High | No | Silent films, German Expressionism, art films |
| **Mochi 1** | Slow | High | No | Final renders, prompt adherence |
| **HunyuanVideo** | Medium | High | No | Production quality |
| **CogVideoX-5B** | Medium | High | No | General purpose (fallback) |

**Recommendation:**
- Use **LTX-2 19B FP8** for production work with audio sync and camera controls
- Use **WAN 2.2** for silent films or when audio isn't needed (higher visual quality for same VRAM)
- Fallback to Mochi for maximum quality or CogVideoX for compatibility

### LTX-2: Recommended Video Model

[LTX-2](https://github.com/Lightricks/LTX-Video) is a 19B parameter DiT-based audio-video foundation model.

**Model Variants:**

| Model | Size | VRAM | Quality | Recommended For |
|-------|------|------|---------|-----------------|
| **LTX-2 19B FP8** ⭐ | ~19GB (+3-5GB overhead) | 24GB | High | Production (A5000, 720p/1080p ≤12-15s, batch=1) |
| LTX-2 19B FP4 | ~12GB (+3-5GB overhead) | 16GB | High | Faster, slightly less quality (720p ≤10s) |
| LTX-2 BF16 (full) | ~43GB | 40GB+ | Highest | RunPod/A100 only |
| LTX-2 Distilled 2B | ~4GB | 12GB | Medium | Rapid iteration |

**FP8 Compatibility:** Requires compatible CUDA/cuDNN/PyTorch builds. Follow LTX-Video docs for driver requirements.

**Key Features:**
- **Synchronized Audio-Video Generation**: Generates coherent audio + video together
- **Camera Controls**: Dolly, jib, static shots with natural camera motion
- **IC-LoRA**: Style transformations (anime, sketch, etc.) with ~1GB VRAM
- **Keyframe Interpolation**: Morphing between keyframes
- **Pose/Depth/Canny Controls**: Precise composition control (Canny edge detection)
- **Text-to-Video and Image-to-Video**: Both workflows supported

**ComfyUI Templates:**

| Template | Use Case |
|----------|----------|
| `LTX2 Text-to-Video` | Generate from text prompts |
| `LTX2 Image-to-Video` | Animate a still image |
| `LTX2 Canny-to-Video` | Edge detection guided generation |
| `LTX2 Distilled` | Fast iteration, lower VRAM |

**Installation:**
```bash

## Performance Expectations

Video generation is compute-intensive. Plan for overnight batch processing rather than real-time iteration.

### Local Generation Times (RTX A5000, 24GB VRAM)

| Video Length | Resolution | Model | Time |
|--------------|------------|-------|------|
| 5 seconds | HD (720p) | LTX-2 19B FP8 | ~1-1.5 min |
| 10 seconds | HD (720p) | LTX-2 19B FP8 | ~3.5-4.5 min |
| 10 seconds | Full HD (1080p) | LTX-2 19B FP8 | ~5-6.5 min |
| 15 seconds | HD (720p) | LTX-2 19B FP8 | ~6-7.5 min |
| 10 seconds | HD (720p) | WAN 2.2 | ~5-6 min |

**Notes:**
- Timings based on Alex Ziskind's benchmarks (RTX 5080) with +15-25% buffer for A5000
- Audio synchronization adds ~10-15% time vs video-only runs
- IO/storage affects throughput; prefer local NVMe, avoid network mounts

### Realistic Workflow

For a **2-minute film** (12 x 10-second clips):
- Generation time: ~42-54 min (LTX-2, 720p) to ~60-72 min (WAN 2.2)
- With retakes and iterations: **2-4 hours**
- Full production with assembly: **overnight task**

**Recommendation:** Queue video generation as overnight background tasks. Use `/task-monitor` to track progress.

```bash

## RunPod for Large Tasks

Use `/ops-runpod` when local generation would cause OOM errors.

### When to Use RunPod

| Scenario | Local (A5000 24GB) | RunPod Needed |
|----------|-------------------|---------------|
| LTX-2 19B FP8, 10-sec HD | Works | No |
| LTX-2 19B FP8, 15-sec 1080p | Works (batch=1) | No |
| 1080p clips >12-15 sec (FP8) | May OOM | Prefer 720p or split; RunPod optional |
| LTX-2 BF16 (43GB full model) | OOM | Yes (A100 40GB+) |
| Very long videos (>20 sec 1080p) | Likely OOM | Yes |
| Batch processing (10+ clips) | Slow but works | Optional (faster) |
| WAN 2.2 + LTX-2 parallel | High OOM risk | Prefer sequential or RunPod |

**OOM Threshold Guidance (A5000 24GB):**
- LTX-2 FP8: 1080p clips over ~12-15s may OOM with audio; use 720p, shorten clips, or disable audio
- Control nets (pose/depth/canny) and multiple LoRAs increase memory; enable selectively
- Monitor runtime VRAM; keep ≤22GB to avoid instability

### RunPod Workflow

```bash
