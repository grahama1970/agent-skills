---
name: tts-train
description: >
  Build TTS datasets and train voice models (Qwen3-TTS, XTTS-v2) from audiobooks or curated clips.
  Use for voice cloning, dataset prep, WhisperX alignment, Qwen3-TTS/XTTS training, and inference.
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
  - qwen3 tts training
  - qwen tts training
  - tts fine tune
metadata:
  short-description: End-to-end TTS dataset prep + training workflow for Qwen3-TTS and XTTS
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

## Training (Qwen3-TTS)

Qwen3-TTS provides better quality and more natural speech. Requires proper audio_codes format:

```bash
# Convert existing manifest to Qwen3-TTS format with audio_codes
.agent/skills/tts-train/run.sh convert-qwen3 \
  datasets/<voice>/train_manifest.jsonl \
  datasets/<voice>/train_manifest_qwen3.jsonl

# Train Qwen3-TTS model
.agent/skills/tts-train/run.sh train-qwen3 \
  --base-model Qwen/Qwen3-TTS-12Hz-0.6B-Base \
  --data-manifest datasets/<voice>/train_manifest_qwen3.jsonl \
  --out-dir artifacts/tts/<voice>_qwen3 \
  --epochs 5 --batch-size 8 --lr 1e-4
```

**Audio Codes Format**: Qwen3-TTS tokenizer returns `audio_codes` as `List[torch.LongTensor]` with shape `[time_steps, 16_quantizers]`. Extract with `enc.audio_codes[0].cpu().tolist()`.

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

## Troubleshooting

### Qwen3-TTS 0.6B Model Training Issues

**Critical**: The official `sft_12hz.py` script only works with 1.7B model out-of-the-box. For 0.6B conversational model, you MUST patch the training script.

**Problem**: RuntimeError: The size of tensor a (2048) must match the size of tensor b (1024)

**Cause**: 0.6B model has `text_hidden_size=2048` but `hidden_size=1024`. The training script tries to add text and codec embeddings with mismatched dimensions.

**Fix**: Apply text_projection before combining embeddings. In [`sft_12hz.py`](/home/graham/workspace/experiments/pi-mono/.pi/skills/tts-train/Qwen3-TTS/finetuning/sft_12hz.py):

```python
# Get text embedding and project if dimensions don't match
input_text_embedding_raw = model.talker.model.text_embedding(input_text_ids)
# Use text_projection if available (required for 0.6B model)
if hasattr(model.talker, 'text_projection'):
    input_text_embedding = model.talker.text_projection(input_text_embedding_raw) * text_embedding_mask
else:
    input_text_embedding = input_text_embedding_raw * text_embedding_mask
```

**Additional Fixes** required for 0.6B training:

1. **Flash Attention**: Set `attn_implementation="eager"` (not `"flash_attention_2"`)
2. **Ref Mels Padding**: Pad variable-length audio mels in collate_fn:
   ```python
   max_mel_len = max(mel.shape[1] for mel in ref_mels)
   padded_mels = []
   for mel in ref_mels:
       if mel.shape[1] < max_mel_len:
           pad_size = max_mel_len - mel.shape[1]
           mel = torch.nn.functional.pad(mel, (0, 0, 0, pad_size))
       padded_mels.append(mel)
   ref_mels = torch.cat(padded_mels, dim=0)
   ```
3. **Checkpoint Saving**: Use cached model path instead of HF string:
   ```python
   from huggingface_hub import snapshot_download
   cached_model_path = snapshot_download(MODEL_PATH, local_files_only=True, ignore_patterns=["*.bin", "*.safetensors"])
   shutil.copytree(cached_model_path, output_dir, dirs_exist_ok=True)
   ```

### CUDA Library Error: libcudnn_ops_infer.so.8

If faster-whisper/WhisperX crashes with:

```
Could not load library libcudnn_ops_infer.so.8: cannot open shared object file
```

**Fix**: Set LD_LIBRARY_PATH before running:

```bash
export LD_LIBRARY_PATH=$(python -c 'import os; import nvidia.cublas.lib; import nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__) + ":" + os.path.dirname(nvidia.cudnn.lib.__file__))')
```

Or use the Docker container with cuDNN pre-installed:

```bash
docker run --rm -it --gpus all -v $(pwd):/workspace memory-tts:cu121 python ...
```

### Too Many Short Segments (Low Clip Yield)

Whisper's VAD often produces very short segments (1-1.5s) that get rejected by the
`--min-sec 1.5` threshold. **Merge adjacent segments** before extraction:

```python
# Merge segments with gap < 0.5s until 2-10s target duration
MIN_TARGET, MAX_TARGET, MAX_GAP = 2.0, 10.0, 0.5
merged = []
current = None
for seg in segments:
    if current is None:
        current = seg.copy()
        continue
    gap = seg['start'] - current['end']
    combined_dur = seg['end'] - current['start']
    if gap <= MAX_GAP and combined_dur <= MAX_TARGET and (current['end'] - current['start']) < MIN_TARGET:
        current['end'] = seg['end']
        current['text'] += ' ' + seg['text']
    else:
        merged.append(current)
        current = seg.copy()
if current:
    merged.append(current)
```

This typically reduces 44k segments → 22k with mean 2s duration, greatly improving yield.

### Using Pre-existing Segments

Skip transcription if you already have segments:

```bash
.agent/skills/tts-train/run.sh ingest \
  <audio.m4b> <voice_name> <output_dir> \
  --segments-jsonl existing_segments.jsonl
```

### XTTS GPTTrainer NaN Loss

If XTTS training shows `loss: nan` from step 0:

```
loss_text_ce: nan  (nan)
loss_mel_ce: nan  (nan)
loss: nan  (nan)
```

**Cause**: Mixed precision (fp16) causes numerical instability with GPTTrainer.

**Fix**: Disable mixed precision in your training config:

```python
trainer_config = GPTTrainerConfig(
    ...
    mixed_precision=False,  # CRITICAL: fp16 causes NaN
    precision="float32",
    ...
)
```

Trade-off: ~2x slower but numerically stable. Reference: [GitHub Issue #3988](https://github.com/coqui-ai/TTS/issues/3988)

### XTTS Model Size Mismatch

If you get size mismatch errors loading checkpoint:

```
RuntimeError: size mismatch for gpt.mel_embedding.weight: copying a param with shape torch.Size([1026, 1024]) from checkpoint, the shape in current model is torch.Size([8194, 1024])
```

**Cause**: Using `XttsConfig` instead of `GPTTrainerConfig`, or wrong model args.

**Fix**: Use `GPTTrainer` with correct `GPTArgs`:

```python
from TTS.tts.layers.xtts.trainer.gpt_trainer import (
    GPTArgs, GPTTrainer, GPTTrainerConfig, XttsAudioConfig
)

model_args = GPTArgs(
    gpt_num_audio_tokens=1026,  # Must match pre-trained
    gpt_start_audio_token=1024,
    gpt_stop_audio_token=1025,
    ...
)
```

### Missing dvae.pth for Training

If you get:

```
RuntimeError: You need to specify config.model_args.dvae_checkpoint path
```

**Fix**: Download the training checkpoint files from HuggingFace:

```bash
cd ~/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2/
wget https://huggingface.co/coqui/XTTS-v2/resolve/main/dvae.pth
wget https://huggingface.co/coqui/XTTS-v2/resolve/main/mel_stats.pth
```

The inference model only includes `model.pth` and `vocab.json`. Training requires `dvae.pth` and `mel_stats.pth`.

### Recommended Training Config

For efficient XTTS fine-tuning:

- `batch_size * grad_accumulation >= 252`
- `learning_rate = 5e-6` (not higher!)
- `mixed_precision = False` (fp16 causes NaN)
- Audio at 22050Hz input, 24000Hz output

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
