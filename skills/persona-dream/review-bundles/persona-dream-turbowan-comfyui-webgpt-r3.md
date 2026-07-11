# WebGPT Review Request: Persona Dream TurboWan/ComfyUI Pipeline R3

## Role

You are the external technical reviewer for a project agent implementing a
receipt-backed persona-dream video pipeline. Please use your web search tools
to confirm current facts before giving recommendations. Do not assume the
project agent's earlier Chutes/TurboWan interpretation is correct.

## Goal

Produce one verified approximately 30-second dream video:

- Horus and Embry having tea under a patio umbrella on a Warhammer-40k-like void world.
- Tyranids are playing in the background, non-threatening.
- Horus and Embry speak warmly and personally about creating the SPARTA Explorer app.
- Final video is assembled from short clips, with receipts and continuity checks.

## Current Local Artifacts

Current planning artifacts:

```text
dream_story.md
dream_story.json
character_scene_bible.json
storyboard.json
timed_transcript.json
multimodal_prompts.json
pipeline_stage_report.json
pipeline_stage_report.md
contact_sheet.png
backend_readiness_receipt.json
manifest.json
```

Deterministic planning gate currently verifies:

```text
4 shots
7.5 seconds per shot
121 frames per shot
30 seconds total
character_scene_bible exists
self_improvement_loop exists
```

## Important Correction To Verify

The user corrected the backend direction:

```text
Chutes does not provide a TurboWan2I2V model.
TurboDiffusion Wan2.2-A14B-720P is an I2V model.
TurboDiffusion/TurboWan2.2 should run through ComfyUI, not Chutes.
Chutes Wan examples are a different non-Turbo Wan2.1 lane.
```

## Operator Preference To Respect

The operator prefers Chutes models over local generation when Chutes has an
appropriate model, because the account has about 5000 calls/day available for
SPARTA Explorer related tasks. Evaluate this preference explicitly:

```text
Prefer Chutes if it has a current, suitable image/video model for this exact
dream pipeline.
Prefer local/containerized ComfyUI only if the needed TurboDiffusion Wan2.2 I2V
model is not available through Chutes or if ComfyUI is materially better for
workflow control, continuity repair, and receipts.
```

The candidate ComfyUI I2V layout is:

```text
ComfyUI/models/diffusion_models/
  TurboWan2.2-I2V-A14B-720P.gguf

OR:

ComfyUI/models/diffusion_models/
  wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors
  wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors

ComfyUI/models/text_encoders/
  umt5_xxl_fp8_e4m3fn_scaled.safetensors

ComfyUI/models/vae/
  wan_2.1_vae.safetensors
```

Candidate model/repo names from the user:

```text
TurboDiffusion/TurboWan2.2-I2V-A14B-720P
vantagewithai/TurboWan2.2-I2V-A14B-720P-ComfyUI-GGUF
Wan-AI/Wan2.2-I2V-A14B
```

Candidate runtime:

```text
ComfyUI API
Wan22ImageToVideoLatent
1280x720
81 frames for 5-second clips
121 frames for approximately 7.5-second clips if stable
4 sampling steps
RTX A5000 24GB
```

## Current Backend Evidence

The current readiness receipt says:

```text
scillm is healthy on localhost:4001
scillm exposes chat/VLM metadata, not image/video generation endpoints
Chutes budget is available
Chutes model search for z-image and wan returned []
ComfyUI API is not running on 127.0.0.1:8188
ComfyUI blueprints exist for:
  Text to Image (Z-Image-Turbo).json
  Pose to Image (Z-Image-Turbo).json
  Image to Video (Wan 2.2).json
  Text to Video (Wan 2.2).json
ComfyUI model directories currently appear placeholder-only
```

ComfyUI Docker lane added locally with these source artifacts:

```text
persona-dream ComfyUI Dockerfile
persona-dream ComfyUI docker-compose file
persona-dream ComfyUI README
```

Compose config validation passes:

```text
docker compose config
```

## Current Agent Questions

Please use web search and answer with concrete implementation guidance:

1. Is the corrected direction right?
   - TurboDiffusion Wan2.2-A14B-720P I2V through ComfyUI as the preferred TurboWan backend.
   - Chutes is not the TurboWan2.2 path unless current web evidence says otherwise.
   - Given the operator's 5000 calls/day Chutes budget, is there a better Chutes-hosted model/path for this dream pipeline?

2. Which exact model files should the agent download or mount for ComfyUI?
   - Include preferred GGUF vs fp8/high-low-noise layout.
   - Include exact ComfyUI subdirectories.
   - Include any known ComfyUI custom nodes or native node requirements.

3. What is the exact ComfyUI API workflow shape the project agent should create?
   - UI workflow JSON vs API prompt JSON.
   - Required nodes.
   - Which fields the agent should patch per shot: image path, prompt, seed, frames, width, height, steps.
   - How to poll and collect outputs.

4. Please provide starter pipeline code/pseudocode suitable for the local repo:
   - `ensure_comfyui_ready()`
   - `submit_comfyui_prompt()`
   - `poll_comfyui_history()`
   - `generate_keyframe()`
   - `generate_i2v_clip()`
   - `continuity_check(previous_clip_or_keyframe, current_clip_or_keyframe, bible)`
   - `ffmpeg_stitch(clips)`
   - artifact receipt schema for each step.

5. What should the self-improvement loop do when generated scene N is inconsistent with scene N-1?
   - Specify repair prompt strategy.
   - Specify when to regenerate keyframe vs regenerate I2V from same keyframe.
   - Specify when to split a 7.5-second clip into 5-second clips.

6. What should remain in `$scillm`?
   - Should scillm be used only for VLM/LLM continuity review?
   - Should image/video generation be ComfyUI API directly?
   - Any caller metadata/logging requirements the agent should preserve?

## Required Output Format

Return:

```text
VERDICT: PASS | NEEDS_CHANGES | BLOCKED

## Web-Verified Findings
...

## Corrected Backend Plan
...

## Chutes-vs-ComfyUI Recommendation
...

## Exact Model File Plan
...

## ComfyUI API Workflow Plan
...

## Pipeline Code Sketch
...

## Continuity/Self-Improvement Loop
...

## Risks And Required Local Proof
...
```

Please cite sources for web-verified claims. Do not mark the overall dream-video
goal complete; this is only a backend/pipeline review.
