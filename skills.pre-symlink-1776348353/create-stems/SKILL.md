---
name: create-stems
description: >
  Audio stem separation using Demucs (4-stem or 6-stem) and optional UVR ensemble.
  Uses the Python API entrypoint for clean error handling. GPU-accelerated, local-first.
allowed-tools: [Bash, Read, Write, Task]
triggers:
  - separate stems
  - stem separation
  - demucs
  - split audio
  - extract vocals
  - create stems
metadata:
  short-description: "Stem separation (Demucs 6s + UVR)"
  author: "Horus"
  version: "0.1.0"

provides:
  - create-stems
composes:
  - learn-artist
  - learn-voice
  - discover-music
  - task-monitor
---

# create-stems

Audio stem separation using Demucs' Python API. Default model is `htdemucs_6s` which splits audio into 6 sources: vocals, drums, bass, other, guitar, piano.

## Usage

```bash
# 6-source separation (default)
./run.sh separate --mix song.wav --out ./stems

# Extract a specific instrument by name (auto-maps to Demucs source)
./run.sh separate --mix song.wav --out ./stems --instrument vocals
./run.sh separate --mix song.wav --out ./stems --instrument oud
./run.sh separate --mix song.wav --out ./stems --instrument piano

# Raw two-stems mode (if you know the Demucs source name)
./run.sh separate --mix song.wav --out ./stems --two-stems guitar

# 4-source with VRAM control
./run.sh separate --mix song.wav --out ./stems --model htdemucs --segment 12

# Quality mode (GPU recommended)
./run.sh separate --mix song.wav --out ./stems --shifts 2

# MP3 output
./run.sh separate --mix song.wav --out ./stems --mp3

# Low-VRAM mode
./run.sh separate --mix song.wav --out ./stems --segment 8 --no-cuda-mem-caching
```

## Instrument Mapping

Use `--instrument` with natural names. The skill maps them to the closest Demucs source:

| Instrument | Maps to (6s) | Notes |
|------------|-------------|-------|
| vocals, voice, singing | vocals | |
| drums, percussion | drums | |
| bass, upright bass, bass guitar | bass | |
| guitar, oud, lute, banjo, mandolin, sitar, ukulele, bouzouki | guitar | Plucked strings |
| piano, keyboard, keys, organ, synth, accordion, harpsichord | piano | Keyboard family |
| violin, cello, trumpet, sax, flute, strings, brass, woodwind | other | Orchestral/misc |

This means an agent can say `--instrument oud` and the skill determines the best extraction path (`--two-stems guitar` on `htdemucs_6s`).

## Models

| Model | Sources | Notes |
|-------|---------|-------|
| `htdemucs_6s` | 6 (vocals/drums/bass/other/guitar/piano) | Default. Best for full separation. |
| `htdemucs` | 4 (vocals/drums/bass/other) | Faster. Guitar+piano in "other". |
| `htdemucs_ft` | 4 (fine-tuned) | Higher quality 4-stem. |

## VRAM Tuning

| Flag | Effect |
|------|--------|
| `--segment N` | Split size (seconds). Smaller = less VRAM. Try 8-12 for 8GB cards. |
| `--overlap F` | Window overlap (default 0.25). Reduce for speed. |
| `--shifts N` | Random time-shift averaging. Higher = better quality, slower. |
| `--jobs N` | Parallel jobs. Increases RAM proportionally. |
| `--no-cuda-mem-caching` | Sets `PYTORCH_NO_CUDA_MEMORY_CACHING=1`. Helps with very low VRAM. |

## Output Structure

```
<out_dir>/
  htdemucs_6s/
    <track_name>/
      vocals.wav
      drums.wav
      bass.wav
      other.wav
      guitar.wav
      piano.wav
  manifest.json
```

## Sanity Checks

```bash
./sanity.sh        # Full environment check
```

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| VRAM | 4GB (with --segment 8) | 8GB+ |
| RAM | 8GB | 16GB+ |
| Storage | 5GB (model cache) | 10GB+ |

## Integration

Used by:
- **create-music** - stem separation step in music creation pipeline
- **discover-music** - `youtube-stems` command delegates here
- **learn-artist** - vocal/instrument extraction for RVC training

## References

- [Demucs](https://github.com/facebookresearch/demucs)
- [python-audio-separator (UVR)](https://github.com/nomadkaraoke/python-audio-separator)
