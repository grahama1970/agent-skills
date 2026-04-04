## Available Skills

Horus has access to all skills in `.pi/skills/`:

| Skill | Purpose in Movie Creation |
|-------|---------------------------|
| `/dogpile` | Deep research on techniques, references |
| `/surf` | Visit websites, tutorials, references |
| `/memory` | Recall prior techniques, store learnings |
| `/create-cast` | Character casting with identity packs (Phase 2.5) |
| `/discover-talent` | Reference actor discovery via TMDB |
| `/create-image` | Generate images for scenes |
| `/create-score` | Generate scene music with HMT bridges |
| `/create-story` | Generate screenplays and narratives |
| `/tts-train` | Horus's voice for narration |
| `/ingest-movie` | Ingest reference movies for style analysis |
| `/episodic-archiver` | Archive movie creation sessions |
| `/anvil` | Debug and harden custom tools |
| `/ingest-book` | Search books for story inspiration |

## Free/Open-Source Tools

| Purpose | Tool |
|---------|------|
| Image Generation | Stable Diffusion (ComfyUI), `/create-image` (FAL SDK) |
| Video Generation | Google Veo (via HorusShotSpec), LTX-2 (local) |
| Video Processing | FFmpeg |
| Music Generation | `/create-score` (ACE-Step via Docker) |
| Speech-to-Text | faster-whisper |
| Text-to-Speech | `/tts-train` (Horus voice) |

See [MODELS.md](MODELS.md) for the video model selection guide, VRAM requirements, camera controls, WAN 2.2, performance expectations, and RunPod usage.

---

# ComfyUI (recommended)
# Install "LTX-Video" from ComfyUI Manager
# Templates appear automatically

# Or standalone
pip install ltx-video
```

**ComfyUI VRAM Optimization Flags:**
```bash
# Reserve VRAM for other operations (prevents OOM during generation)
python -m main --reserve-vram 5

# Low VRAM mode - offloads to system RAM (slower but prevents OOM)
python -m main --lowvram

# Weight streaming - NVIDIA/ComfyUI collaboration for 256GB RAM systems
# Automatically offloads model weights to system RAM when VRAM exhausted
```

**Additional Resources:**
- [ComfyUI_LTX-2_VRAM_Memory_Management](https://github.com/RandomInternetPreson/ComfyUI_LTX-2_VRAM_Memory_Management) - Nodes for long videos on consumer GPUs

### Camera Control Reference (LTX-2)

LTX-2 supports cinematic camera movements via prompt keywords:

| Movement | Prompt Keywords | Effect |
|----------|-----------------|--------|
| **Static** | `static shot`, `locked camera` | Fixed camera position |
| **Dolly** | `dolly in`, `dolly out`, `push in` | Camera moves toward/away from subject |
| **Jib/Crane** | `jib up`, `jib down`, `crane shot` | Vertical camera sweep |
| **Pan** | `pan left`, `pan right` | Horizontal rotation |
| **Tilt** | `tilt up`, `tilt down` | Vertical rotation |
| **Tracking** | `tracking shot`, `follow shot` | Camera follows subject |
| **Zoom** | `zoom in`, `zoom out` | Focal length change |

**Example Prompts:**
```
# Dramatic reveal
"Dolly in slowly to a detective examining evidence, noir lighting, static hold on face"

# Action sequence
"Tracking shot following runner through city streets, handheld, dynamic"

# Interview setup
"Static medium shot, subject centered, shallow depth of field, jib down to hands"
```

**Combining Movements:**
```
"Jib up while dolly out, revealing vast landscape, golden hour, cinematic"
```

### WAN 2.2: Silent Film Alternative

[WAN 2.2](https://github.com/Wan-Video/Wan2.2) is a 14B parameter model optimized for visual quality without audio:

**Best For:**
- Silent films and art cinema
- German Expressionism era aesthetics (Nosferatu, Metropolis, Cabinet of Dr. Caligari)
- High visual fidelity when audio isn't needed
- Projects where audio will be added separately

**Comparison to LTX-2:**
| Aspect | LTX-2 19B FP8 | WAN 2.2 14B |
|--------|---------------|-------------|
| Audio | Synchronized | None |
| Speed (10-sec HD, A5000) | ~3.5-4.5 min | ~5-6 min |
| Visual Quality | High | Very High |
| VRAM (24GB) | Works | Works |

**When to Choose WAN 2.2:**
- Creating silent films with intertitles
- German Expressionism homages
- Music videos where audio is pre-recorded
- Art films with separate sound design

**Practical Notes:** Seed control recommended for stable multi-shot outputs. 720p preferred on 24GB for consistent speeds.

# Example: Run generation overnight
./run.sh generate --script script.json --output-dir ./assets &
# Check progress next morning
```

# Provision GPU for large task
/ops-runpod provision --gpu a100-40gb --task "LTX-2 BF16 generation"

# Run generation on RunPod
/ops-runpod run --script generate.sh

# Download results and terminate
/ops-runpod download --output ./assets
/ops-runpod terminate
```

**RunPod GPU Options:**
- BF16/full precision: A100 40-80GB, H100 (required)
- FP8/FP4 tasks: L40S 48GB, A10G 24GB (cheaper alternatives)

**Cost Consideration:** RunPod charges by the hour. For overnight tasks, local generation is more cost-effective. Consider spot/preemptible instances for savings.

### Troubleshooting & Fallbacks

**OOM Mitigation:**
1. Reduce resolution (720p → 540p)
2. Shorten clip length
3. Set batch=1
4. Switch FP mode (BF16 → FP8 → FP4)
5. Disable audio
6. Split long clips into segments

**Stability:**
- Fix seed for reproducibility
- Avoid parallel jobs on 24GB
- Reduce control nets and LoRA stacks

**Fallback Path:** If LTX-2 fails, switch to WAN 2.2 (video-only) or CogVideoX; add audio separately in post.

## Memory Integration

After each movie, stores:
- Successful prompts
- Working tool code
- Technique insights
- Concept relationships

Scope: `horus-filmmaking`

See [EXAMPLES.md](EXAMPLES.md) for workflow patterns, multi-model collaboration, and example sessions.

---

## Dependencies

- Docker (for isolated code execution)
- FFmpeg (video processing)
- Python 3.11+ (orchestrator)
- GPU recommended (for Stable Diffusion, video models)
