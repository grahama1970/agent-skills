#!/bin/bash
# Retry Qwen3-TTS training for personas that failed (OOM or timeout)
# v2: Runs each phase in separate subprocess to ensure GPU memory is cleared

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${HOME}/miniconda3/bin/python"
LOG="/tmp/retry_failed_training_v2.log"
STORAGE="/mnt/storage12tb/media/personas"

cd "$SCRIPT_DIR"

# Personas that need Qwen3-TTS retry (have PersonaPlex but failed Qwen3-TTS)
FAILED_PERSONAS=(
    "Viola Davis"
    "Akira Kurosawa"
    "Wong Kar-wai"
    "Jean-Luc Godard"
    "Kurt Vonnegut"
    "Donald Knuth"
    "Joseph Campbell"
    "Stefan Sagmeister"
)

clear_gpu() {
    $PYTHON -c "import torch; torch.cuda.empty_cache(); torch.cuda.synchronize()" 2>/dev/null || true
    # Also kill any lingering Python processes using GPU
    nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | while read pid; do
        if [ -n "$pid" ]; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    sleep 2
}

echo "=== Retrying Failed Qwen3-TTS Training (v2) ===" | tee -a "$LOG"
echo "Started at $(date)" | tee -a "$LOG"
echo "" | tee -a "$LOG"

for persona in "${FAILED_PERSONAS[@]}"; do
    slug=$(echo "$persona" | tr '[:upper:]' '[:lower:]' | tr ' ' '_')
    persona_dir="$STORAGE/$slug"

    echo "--- Processing: $persona ---" | tee -a "$LOG"

    # Clear GPU before starting
    echo "  Clearing GPU memory..." | tee -a "$LOG"
    clear_gpu

    # Check if PersonaPlex already exists (skip extraction)
    personaplex_dir="$persona_dir/personaplex"
    has_personaplex=false
    if [ -d "$personaplex_dir" ] && [ -n "$(ls -A $personaplex_dir/*.pt 2>/dev/null)" ]; then
        echo "  PersonaPlex already exists, skipping extraction" | tee -a "$LOG"
        has_personaplex=true
    fi

    # Remove old training data to regenerate with fixed ref_audio
    if [ -d "$persona_dir/tts_training" ]; then
        echo "  Removing old tts_training data..." | tee -a "$LOG"
        rm -rf "$persona_dir/tts_training"
    fi

    if [ -d "$persona_dir/qwen3_tts" ]; then
        echo "  Removing old qwen3_tts data..." | tee -a "$LOG"
        rm -rf "$persona_dir/qwen3_tts"
    fi

    # Step 1: Generate training data (transcription) - runs in subprocess
    echo "  Step 1: Generating training data..." | tee -a "$LOG"
    $PYTHON -c "
import subprocess
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from train import generate_training_data_from_clips, get_persona_dir, VoiceReference, discover_youtube_clips
from pathlib import Path

persona = '$persona'
persona_dir = get_persona_dir(persona)
tts_dir = persona_dir / 'tts_training'
tts_dir.mkdir(parents=True, exist_ok=True)

# Get cached clips
cache_dir = Path.home() / '.cache/personaplex'
clips = list((cache_dir / 'audio' / persona.lower().replace(' ', '_')).glob('*.wav'))

if clips:
    refs = [VoiceReference(actor=persona, clips=clips)]
    result = generate_training_data_from_clips(persona, refs, tts_dir)
    print(f'Generated: {result}')
else:
    print(f'No clips found for {persona}')
" 2>&1 | tee -a "$LOG"

    # Clear GPU after transcription
    echo "  Clearing GPU after transcription..." | tee -a "$LOG"
    clear_gpu

    # Step 2: Prepare Qwen3-TTS data (audio codes) - runs in subprocess
    echo "  Step 2: Preparing Qwen3-TTS data..." | tee -a "$LOG"
    manifest="$persona_dir/tts_training/${slug}_combined.jsonl"
    qwen3_manifest="$persona_dir/qwen3_tts/${slug}_manifest_qwen3.jsonl"

    if [ -f "$manifest" ]; then
        mkdir -p "$persona_dir/qwen3_tts"
        $PYTHON Qwen3-TTS/finetuning/prepare_data.py \
            --device cuda:0 \
            --tokenizer_model_path Qwen/Qwen3-TTS-Tokenizer-12Hz \
            --input_jsonl "$manifest" \
            --output_jsonl "$qwen3_manifest" 2>&1 | tee -a "$LOG"
    else
        echo "  No manifest found, skipping prepare_data" | tee -a "$LOG"
        continue
    fi

    # Clear GPU after data prep
    echo "  Clearing GPU after data prep..." | tee -a "$LOG"
    clear_gpu

    # Step 3: Train Qwen3-TTS - runs in subprocess
    echo "  Step 3: Training Qwen3-TTS..." | tee -a "$LOG"
    if [ -f "$qwen3_manifest" ]; then
        timeout 7200 $PYTHON Qwen3-TTS/finetuning/sft_12hz.py \
            --init_model_path Qwen/Qwen3-TTS-12Hz-1.7B-Base \
            --train_jsonl "$qwen3_manifest" \
            --output_model_path "$persona_dir/qwen3_tts/model" \
            --num_epochs 3 \
            --batch_size 1 \
            --lr 2e-5 \
            --gradient_accumulation_steps 8 \
            --gradient_checkpointing \
            --speaker_name "$slug" 2>&1 | tee -a "$LOG" || echo "  Training timeout or error" | tee -a "$LOG"
    else
        echo "  No Qwen3 manifest found, skipping training" | tee -a "$LOG"
    fi

    # Clear GPU after training
    echo "  Clearing GPU after training..." | tee -a "$LOG"
    clear_gpu

    echo "  Completed: $persona" | tee -a "$LOG"
    echo "" | tee -a "$LOG"
done

echo "=== All Retries Complete ===" | tee -a "$LOG"
echo "Completed at $(date)" | tee -a "$LOG"

# Show final status
$PYTHON batch_train.py status
