---
name: tts-horus
description: >
  Build and operate the Horus TTS pipeline from cleared audiobooks.
  Includes dataset prep, WhisperX alignment, XTTS training, voice coloring,
  and persona inference helpers.
allowed-tools: Bash, Read
triggers:
  - horus tts
  - build horus voice
  - voice coloring
  - tts pipeline
metadata:
  short-description: Horus TTS dataset + training + inference pipeline
---

# Horus TTS Pipeline

This skill standardizes the end-to-end Horus voice workflow using `uvx`-style
invocations so dependencies are isolated per command. It assumes recordings
live under `persona/data/audiobooks/` with per-book `clean/` folders.

## Commands

### `dataset`
Builds the Horus dataset from Vengeful Spirit using faster-whisper segmentation.

```bash
python run/tts/ingest_audiobook.py \
  --audio persona/data/audiobooks/Vengeful_Spirit_The_Horus_Heresy_Book_29-LC_64_22050_stereo/audio.m4b \
  --book-name Vengeful_Spirit_The_Horus_Heresy_Book_29 \
  --output-dir datasets/horus_voice \
  --max-hours 0
```

### `align`
Runs WhisperX alignment with lexicon overrides.

```bash
python run/tts/align_transcripts.py \
  --manifest datasets/horus_voice/train_manifest.jsonl \
  --output datasets/horus_voice/train_aligned.jsonl \
  --dataset-root datasets/horus_voice \
  --lexicon persona/docs/lexicon_overrides.json \
  --strategy whisperx --device cuda
```

### `train`
Fine-tunes XTTS-v2 (local A5000 by default).

```bash
python run/tts/train_xtts.py --config configs/tts/horus_xtts.yaml --simulate False
```

### `say`
CLI synthesis (writes `.artifacts/tts/output.wav` by default).

```bash
python run/tts/say.py "Lupercal speaks."
```

### `server`
FastAPI server for low-latency synthesis.

```bash
python run/tts/server.py
```

### `color`
Voice coloring helper (to be implemented in Task 5).

```bash
python run/tts/color_voice.py --base horus --color warm --alpha 0.4
```

## Notes

- WhisperX is installed in the project `.venv`; for standalone runs, use `uvx whisperx` if needed.
- Golden samples live in `tests/fixtures/tts/golden/` (Git LFS).
- Orchestrate-ready task plan lives at `persona/docs/tasks/0N_voice_coloring.md`.
