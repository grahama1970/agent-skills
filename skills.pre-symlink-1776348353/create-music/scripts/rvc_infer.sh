#!/usr/bin/env bash
#
# RVC Inference Script
# Run voice conversion on audio files
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
RVC_DIR="${SKILL_DIR}/rvc"

usage() {
    cat <<EOF
Usage: rvc_infer.sh [options]

Options:
  --model-name NAME       RVC model name (required)
  --input FILE            Input audio file (required)
  --output FILE           Output audio file (required)
  --pitch N               Pitch shift in semitones (default: 0)
  --f0method METHOD       F0 extraction method: harvest, pm, crepe, rmvpe (default: rmvpe)
  --index-rate RATE       Index rate 0.0-1.0 (default: 0.75)

Example:
  ./rvc_infer.sh --model-name nico-500 --input vocals.wav --output converted.wav --pitch -2
EOF
}

# Defaults
MODEL_NAME=""
INPUT_FILE=""
OUTPUT_FILE=""
PITCH=0
F0_METHOD="rmvpe"
INDEX_RATE=0.75

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --model-name)
            MODEL_NAME="$2"
            shift 2
            ;;
        --input)
            INPUT_FILE="$2"
            shift 2
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --pitch)
            PITCH="$2"
            shift 2
            ;;
        --f0method)
            F0_METHOD="$2"
            shift 2
            ;;
        --index-rate)
            INDEX_RATE="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate required args
if [[ -z "$MODEL_NAME" ]] || [[ -z "$INPUT_FILE" ]] || [[ -z "$OUTPUT_FILE" ]]; then
    echo "Error: --model-name, --input, and --output are required"
    usage
    exit 1
fi

if [[ ! -f "$INPUT_FILE" ]]; then
    echo "Error: Input file not found: $INPUT_FILE"
    exit 1
fi

if [[ ! -d "$RVC_DIR" ]]; then
    echo "Error: RVC not set up. Run: ./run.sh rvc-setup"
    exit 1
fi

# Find model and index files
WEIGHT_ROOT="${RVC_DIR}/assets/weights"
INDEX_ROOT="${RVC_DIR}/logs"

# Find model .pth file
MODEL_PATH=$(find "${WEIGHT_ROOT}" -name "${MODEL_NAME}*.pth" 2>/dev/null | head -1)
if [[ -z "$MODEL_PATH" ]]; then
    echo "Error: Model not found: ${MODEL_NAME}"
    echo "Available models in ${WEIGHT_ROOT}:"
    ls -1 "${WEIGHT_ROOT}"/*.pth 2>/dev/null || echo "  (none)"
    exit 1
fi

# Find newest index file for this model
INDEX_PATH=$(find "${INDEX_ROOT}" -name "added_*.index" -path "*${MODEL_NAME}*" 2>/dev/null | sort -r | head -1)
if [[ -z "$INDEX_PATH" ]]; then
    echo "Warning: No index file found for ${MODEL_NAME}, proceeding without index"
    INDEX_PATH=""
fi

echo "=== RVC Inference ==="
echo "Model: ${MODEL_PATH}"
echo "Index: ${INDEX_PATH:-none}"
echo "Input: ${INPUT_FILE}"
echo "Output: ${OUTPUT_FILE}"
echo "Pitch: ${PITCH}"
echo "F0 Method: ${F0_METHOD}"
echo ""

cd "${RVC_DIR}"

# Run inference
python tools/infer_cli.py \
    --f0up_key "${PITCH}" \
    --input_path "$(realpath "$INPUT_FILE")" \
    --opt_path "$(realpath "$OUTPUT_FILE")" \
    --model_name "$(basename "$MODEL_PATH")" \
    --index_path "${INDEX_PATH}" \
    --index_rate "${INDEX_RATE}" \
    --f0method "${F0_METHOD}" \
    --device "cuda:0"

echo ""
echo "=== RVC Inference Complete ==="
echo "Output: ${OUTPUT_FILE}"
