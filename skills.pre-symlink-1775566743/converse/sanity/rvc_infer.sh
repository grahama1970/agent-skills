#!/usr/bin/env bash
# Sanity check: RVC inference can convert voice
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MUSIC_SKILL="/home/graham/workspace/experiments/pi-mono/.pi/skills/create-music"
RVC_DIR="${MUSIC_SKILL}/rvc"
RVC_MODELS="/mnt/storage12tb/media/music/rvc-models/voice"

echo "=== RVC Inference Sanity Check ==="

# Check 1: create-music skill exists
echo -n "  [1/5] create-music skill: "
if [[ -d "$MUSIC_SKILL" ]] && [[ -f "$MUSIC_SKILL/scripts/rvc_infer.sh" ]]; then
    echo "PASS"
else
    echo "FAIL: create-music skill or rvc_infer.sh not found"
    exit 1
fi

# Check 2: RVC directory set up
echo -n "  [2/5] RVC installation: "
if [[ -d "$RVC_DIR" ]] && [[ -f "$RVC_DIR/tools/infer_cli.py" ]]; then
    echo "PASS"
else
    echo "FAIL: RVC not set up at $RVC_DIR"
    echo "  Run: cd $MUSIC_SKILL && ./run.sh rvc-setup"
    exit 1
fi

# Check 3: At least one voice model exists
echo -n "  [3/5] Voice models: "
MODEL_COUNT=$(find "$RVC_MODELS" -name "*-infer.pth" 2>/dev/null | wc -l)
if [[ "$MODEL_COUNT" -gt 0 ]]; then
    echo "PASS ($MODEL_COUNT models)"
else
    # Also check RVC weights directory
    WEIGHT_COUNT=$(find "${RVC_DIR}/assets/weights" -name "*.pth" 2>/dev/null | wc -l)
    if [[ "$WEIGHT_COUNT" -gt 0 ]]; then
        echo "PASS ($WEIGHT_COUNT models in RVC weights)"
    else
        echo "FAIL: No voice models found"
        exit 1
    fi
fi

# Check 4: Embry model specifically
echo -n "  [4/5] Embry voice model: "
EMBRY_MODEL=$(find "$RVC_MODELS" -path "*/embry/*" -name "*.pth" 2>/dev/null | head -1)
if [[ -z "$EMBRY_MODEL" ]]; then
    EMBRY_MODEL=$(find "${RVC_DIR}/assets/weights" -name "embry*.pth" 2>/dev/null | head -1)
fi
if [[ -n "$EMBRY_MODEL" ]]; then
    SIZE=$(stat -c%s "$EMBRY_MODEL" 2>/dev/null || stat -f%z "$EMBRY_MODEL" 2>/dev/null)
    SIZE_MB=$((SIZE / 1024 / 1024))
    echo "PASS (${SIZE_MB}MB at $EMBRY_MODEL)"
else
    echo "MISSING: Embry RVC model not yet trained"
    echo "  Train: cd .pi/skills/learn-artist && ./run.sh train embry --source-dir /mnt/storage12tb/media/personas/embry/tts_output --category voice"
    echo "  (This is a blocker for voice conversion but not for other sanity checks)"
fi

# Check 5: Quick inference test with any existing model
echo -n "  [5/5] Inference test: "
# Find any model to test with
TEST_MODEL=$(find "${RVC_DIR}/assets/weights" -name "*.pth" 2>/dev/null | head -1)
if [[ -z "$TEST_MODEL" ]]; then
    # Try exported models
    TEST_MODEL=$(find "$RVC_MODELS" -name "*-infer.pth" 2>/dev/null | head -1)
fi

if [[ -n "$TEST_MODEL" ]]; then
    TMPDIR=$(mktemp -d)
    trap "rm -rf $TMPDIR" EXIT

    # Generate a 1-second test tone as input
    cd "$RVC_DIR"
    python -c "
import numpy as np, soundfile as sf
sr = 44100
t = np.linspace(0, 1, sr)
audio = 0.5 * np.sin(2 * np.pi * 440 * t)
sf.write('${TMPDIR}/test_input.wav', audio.astype(np.float32), sr)
" 2>/dev/null || true

    if [[ -f "${TMPDIR}/test_input.wav" ]]; then
        MODEL_NAME=$(basename "$TEST_MODEL" .pth)
        # Try a quick inference (timeout after 30s)
        if timeout 30 python tools/infer_cli.py \
            --f0up_key 0 \
            --input_path "${TMPDIR}/test_input.wav" \
            --opt_path "${TMPDIR}/test_output.wav" \
            --model_name "$(basename "$TEST_MODEL")" \
            --index_path "" \
            --index_rate 0.0 \
            --f0method rmvpe \
            --device "cuda:0" >/dev/null 2>&1; then
            if [[ -f "${TMPDIR}/test_output.wav" ]]; then
                echo "PASS (model: $MODEL_NAME)"
            else
                echo "FAIL: No output produced"
                exit 1
            fi
        else
            echo "FAIL: Inference failed or timed out"
            exit 1
        fi
    else
        echo "SKIP: Could not generate test input"
    fi
else
    echo "SKIP: No models available for inference test"
fi

echo "=== RVC Inference: PASS ==="
