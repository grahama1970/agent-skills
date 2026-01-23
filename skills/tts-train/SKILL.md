---
name: tts-train
description: >
  Build TTS datasets and train voice models (XTTS-v2) from audiobooks or curated clips.
  Use for voice cloning, dataset prep, WhisperX alignment, XTTS training, and inference.
allowed-tools: Bash, Read
triggers:
  - tts train
  - train voice model
  - voice cloning
  - voice model training
  - tts dataset
  - build tts dataset
  - align transcripts
  - xtts training
  - tts fine tune
metadata:
  short-description: End-to-end TTS dataset prep + training workflow
---

# TTS Train Workflow

This skill provides a general, composable workflow for building datasets and training
voice models. It has its own `pyproject.toml` (self-contained) for XTTS + TensorBoard.

Use the bundled `run.sh` so the correct environment is selected per step:
- **Project env** for ingest/alignment (uses `whisperx` + `faster-whisper`).
- **Skill env** for XTTS training/inference + TensorBoard (avoids pandas conflicts).

```bash
.agent/skills/tts-train/run.sh <command> ...
```

## Dataset Build Options

### Option A: Audiobook → Segments (fast path)

Use the audiobook-ingest skill for ingestion, then hand off to TTS:

```bash
.agent/skills/audiobook-ingest/run.sh handoff-tts "<book_dir_name>"
.agent/skills/audiobook-ingest/run.sh align-tts
```

Direct ingest (if you want full control):

```bash
.agent/skills/tts-train/run.sh ingest \
  persona/data/audiobooks/<book>/audio.m4b \
  <voice_name> \
  datasets/<voice_name>
```

### Option B: Curated Clips + Transcripts

Provide a JSONL file with `audio_file` (relative to input dir) and `text`.

```bash
.agent/skills/tts-train/run.sh ingest-transcript \
  data/<voice>/audio_raw \
  data/<voice>/transcripts.jsonl \
  datasets/<voice>
```

## Alignment (WhisperX)

```bash
.agent/skills/tts-train/run.sh align \
  datasets/<voice>/train_manifest.jsonl \
  datasets/<voice>/train_aligned.jsonl \
  datasets/<voice>
```

## Training (XTTS-v2)

```bash
.agent/skills/tts-train/run.sh train-local configs/tts/<voice>_xtts.yaml
```

Copy an existing config (e.g., `configs/tts/horus_xtts.yaml`) and adjust paths/params.

Use RunPod (stub wrapper):

```bash
.agent/skills/tts-train/run.sh train-runpod configs/tts/<voice>_xtts.yaml
```

## Inference

```bash
.agent/skills/tts-train/run.sh infer configs/tts/<voice>_xtts.yaml artifacts/tts/<voice>/<voice>_sample.wav
uv run python run/tts/server.py
```

## TensorBoard (Auto)

```bash
.agent/skills/tts-train/run.sh tensorboard 6006
```

## Long Runs (Scheduler Skill)

For overnight runs, register a scheduler job so training survives terminal drops:

```bash
.agent/skills/scheduler/run.sh register \
  --name "tts-train-<voice>" \
  --interval "12h" \
  --workdir "/home/graham/workspace/experiments/memory" \
  --command ".agent/skills/tts-train/run.sh train-local configs/tts/<voice>_xtts.yaml | tee logs/tts/<voice>_train.log"
```

## Post-Run Reporting (Batch-Report Skill)

If you want a concise dataset report, emit a `.batch_state.json` and run batch-report:

```bash
uv run python - <<'PY'
import json
from pathlib import Path

root = Path("datasets/<voice>")
manifest = root / "train_manifest.jsonl"
rejections = root / "rejections.jsonl"
total = sum(1 for _ in manifest.open()) if manifest.exists() else 0
rejected = sum(1 for _ in rejections.open()) if rejections.exists() else 0
state = {
  "name": "tts-dataset",
  "description": "TTS dataset build summary",
  "total": total + rejected,
  "successful": total,
  "failed": rejected,
}
(root / ".batch_state.json").write_text(json.dumps(state, indent=2))
PY

uv run python .agent/skills/batch-report/report.py summary datasets/<voice>
```
