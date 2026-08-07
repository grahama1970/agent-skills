---
name: create-music
description: >
  AI-assisted music creation for Horus persona. Voice conversion (RVC) and
  music generation (MusicGen/AudioCraft). Stem separation uses create-stems skill.
  Local-first with GPU acceleration.
allowed-tools: [Bash, Read, Write, Task]
triggers:
  - create music
  - make music
  - generate music
  - voice conversion
  - rvc inference
  - musicgen
  - audiocraft
  - clone voice
  - singing voice
metadata:
  short-description: "AI music creation (RVC + MusicGen)"
  author: "Horus"
  version: "0.2.0"

provides:
  - create-music
composes:
  - learn-voice
  - discover-music
  - learn-artist
  - task-monitor
disciplines:
  - content-creation
  - voice-audio
---

# create-music

AI-assisted music creation pipeline for Horus persona. Local-first, GPU-accelerated.

## Capabilities

### 1. Stem Separation (Mix → Parts)

**Moved to `/create-stems` skill.** Use create-stems for all stem separation:

```bash
# In .pi/skills/create-stems/
./run.sh separate --mix input.wav --out work/stems
./run.sh separate --mix input.wav --out work/stems --instrument vocals
./run.sh separate --mix input.wav --out work/stems --instrument oud
```

### 2. Voice Conversion (RVC)

Convert vocals to a trained voice model:

```bash
./run.sh rvc-setup                    # One-time: clone repo + download pretrains
./run.sh rvc-infer \
  --model-name nico-500 \
  --input vocals.wav \
  --output converted.wav \
  --pitch 0 \
  --f0method harvest
```

### 3. Music Generation (MusicGen/AudioCraft)

MusicGen runs in Docker (Python 3.11 container) to avoid dependency conflicts.

```bash
# First run auto-builds the Docker image
./run.sh musicgen \
  --prompt "intimate jazz trio, soft piano" \
  --seconds 30 \
  --out generated.wav

# Or build explicitly
./run.sh musicgen-build

# With fine-tuned checkpoint
./run.sh musicgen \
  --checkpoint-dir /path/to/checkpoint \
  --prompt "intimate jazz trio, soft piano" \
  --seconds 30 \
  --out generated.wav

# Available models (default: facebook/musicgen-small)
./run.sh musicgen --model facebook/musicgen-medium --prompt "..." --out out.wav
```

## Workflow

```
INPUT MIX
    ↓
create-stems separate (Demucs 6s / UVR)
    ↓
rvc-infer on vocals (optional)
    ↓
musicgen for new parts (optional)
    ↓
FINAL OUTPUT
```

## Sanity Checks

```bash
./sanity.sh                           # Full sanity suite
./sanity/check_env.sh                 # ffmpeg + torch + imports
python sanity/check_alignment.py      # stems same SR + frames
python sanity/check_reconstruction.py # mix ≈ sum(stems)
```

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| VRAM | 8GB | 16GB+ |
| RAM | 16GB | 32GB+ |
| Storage | 20GB | 50GB+ |

## References

- [AudioCraft/MusicGen](https://github.com/facebookresearch/audiocraft)
- [Demucs](https://github.com/facebookresearch/demucs)
- [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)
- [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator)
