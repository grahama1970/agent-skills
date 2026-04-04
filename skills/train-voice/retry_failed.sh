#!/bin/bash
# Retry Qwen3-TTS training for personas that failed (OOM or timeout)
# These personas have PersonaPlex but no working Qwen3-TTS model
# Uses fixed training code with:
#   1. Correct loss weighting (0.3 * sub_talker_loss)
#   2. Consistent ref_audio for all samples (official best practice)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="/home/graham/miniconda3/bin/python"
LOG="/tmp/retry_failed_training.log"
STORAGE="/mnt/storage12tb/media/personas"

cd "$SCRIPT_DIR"

# Personas that need Qwen3-TTS retry (have PersonaPlex but no Qwen3-TTS)
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

echo "=== Retrying Failed Qwen3-TTS Training ===" | tee -a "$LOG"
echo "Started at $(date)" | tee -a "$LOG"
echo "" | tee -a "$LOG"

for persona in "${FAILED_PERSONAS[@]}"; do
    slug=$(echo "$persona" | tr '[:upper:]' '[:lower:]' | tr ' ' '_')
    persona_dir="$STORAGE/$slug"

    echo "--- Processing: $persona ---" | tee -a "$LOG"

    # Remove old training data to regenerate with fixed ref_audio
    if [ -d "$persona_dir/tts_training" ]; then
        echo "  Removing old tts_training data..." | tee -a "$LOG"
        rm -rf "$persona_dir/tts_training"
    fi

    if [ -d "$persona_dir/qwen3_tts" ]; then
        echo "  Removing old qwen3_tts data..." | tee -a "$LOG"
        rm -rf "$persona_dir/qwen3_tts"
    fi

    # Clear GPU memory before training
    $PYTHON -c "import torch; torch.cuda.empty_cache(); torch.cuda.synchronize()" 2>/dev/null || true

    # Run training with fixed code
    echo "  Starting training for $persona..." | tee -a "$LOG"
    $PYTHON train.py train "$persona" --references "$persona" --foreground 2>&1 | tee -a "$LOG"

    # Clear GPU memory after training
    $PYTHON -c "import torch; torch.cuda.empty_cache(); torch.cuda.synchronize()" 2>/dev/null || true

    echo "  Completed: $persona" | tee -a "$LOG"
    echo "" | tee -a "$LOG"
done

echo "=== All Retries Complete ===" | tee -a "$LOG"
echo "Completed at $(date)" | tee -a "$LOG"

# Show final status
$PYTHON batch_train.py status
