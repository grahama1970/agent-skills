#!/usr/bin/env bash
#
# RVC Training Script
# Train a voice model from audio files
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
RVC_DIR="${SKILL_DIR}/rvc"

usage() {
    cat <<EOF
Usage: rvc_train.sh [options]

Train an RVC voice model from audio files.

Options:
  --name NAME           Model name (required)
  --input-dir DIR       Directory containing audio files (required)
  --sample-rate SR      Sample rate: 32k, 40k, 48k (default: 40k)
  --epochs N            Total epochs to train (default: 200)
  --batch-size N        Batch size (default: 8)
  --save-every N        Save checkpoint every N epochs (default: 25)
  --f0-method METHOD    F0 extraction: rmvpe, pm, harvest, crepe (default: rmvpe)
  --version VER         RVC version: v1, v2 (default: v2)
  --gpu ID              GPU ID to use (default: 0)

Example:
  ./rvc_train.sh --name billie-holiday --input-dir /path/to/vocals --epochs 300

Pipeline Steps:
  1. Preprocess - Slice audio into training segments
  2. Extract F0 - Extract pitch information
  3. Extract Features - Extract hubert embeddings
  4. Train - Train the voice model
  5. Build Index - Create retrieval index
EOF
}

# Defaults
MODEL_NAME=""
INPUT_DIR=""
SAMPLE_RATE="40k"
TOTAL_EPOCHS=200
BATCH_SIZE=8
SAVE_EVERY=25
F0_METHOD="rmvpe"
VERSION="v2"
GPU_ID="0"
N_PROCS=4

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --name)
            MODEL_NAME="$2"
            shift 2
            ;;
        --input-dir)
            INPUT_DIR="$2"
            shift 2
            ;;
        --sample-rate)
            SAMPLE_RATE="$2"
            shift 2
            ;;
        --epochs)
            TOTAL_EPOCHS="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --save-every)
            SAVE_EVERY="$2"
            shift 2
            ;;
        --f0-method)
            F0_METHOD="$2"
            shift 2
            ;;
        --version)
            VERSION="$2"
            shift 2
            ;;
        --gpu)
            GPU_ID="$2"
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
if [[ -z "$MODEL_NAME" ]] || [[ -z "$INPUT_DIR" ]]; then
    echo "Error: --name and --input-dir are required"
    usage
    exit 1
fi

if [[ ! -d "$INPUT_DIR" ]]; then
    echo "Error: Input directory not found: $INPUT_DIR"
    exit 1
fi

if [[ ! -d "$RVC_DIR" ]]; then
    echo "Error: RVC not set up. Run: ./run.sh rvc-setup"
    exit 1
fi

# Convert sample rate to Hz
case "$SAMPLE_RATE" in
    32k) SR_HZ=32000 ;;
    40k) SR_HZ=40000 ;;
    48k) SR_HZ=48000 ;;
    *)
        echo "Error: Invalid sample rate: $SAMPLE_RATE (use 32k, 40k, or 48k)"
        exit 1
        ;;
esac

# Set up paths
EXP_DIR="${RVC_DIR}/logs/${MODEL_NAME}"
VERSION_SUFFIX=""
[[ "$VERSION" == "v2" ]] && VERSION_SUFFIX="_v2"

# Pretrained model paths
PRETRAINED_G="${RVC_DIR}/assets/pretrained${VERSION_SUFFIX}/f0G${SAMPLE_RATE}.pth"
PRETRAINED_D="${RVC_DIR}/assets/pretrained${VERSION_SUFFIX}/f0D${SAMPLE_RATE}.pth"

echo "=== RVC Training Pipeline ==="
echo "Model:       ${MODEL_NAME}"
echo "Input:       ${INPUT_DIR}"
echo "Sample Rate: ${SAMPLE_RATE} (${SR_HZ} Hz)"
echo "Epochs:      ${TOTAL_EPOCHS}"
echo "Batch Size:  ${BATCH_SIZE}"
echo "F0 Method:   ${F0_METHOD}"
echo "Version:     ${VERSION}"
echo "GPU:         ${GPU_ID}"
echo "Output:      ${EXP_DIR}"
echo ""

cd "${RVC_DIR}"
export CUDA_VISIBLE_DEVICES="${GPU_ID}"

# Step 1: Preprocess
echo "=== Step 1/5: Preprocessing ==="
mkdir -p "${EXP_DIR}"
python infer/modules/train/preprocess.py \
    "${INPUT_DIR}" \
    "${SR_HZ}" \
    "${N_PROCS}" \
    "${EXP_DIR}" \
    "False" \
    3.7

echo "Preprocessing complete. Sliced audio in: ${EXP_DIR}/0_gt_wavs"
echo ""

# Step 2: Extract F0
echo "=== Step 2/5: Extracting F0 (pitch) ==="
if [[ "$F0_METHOD" == "rmvpe" ]]; then
    python infer/modules/train/extract/extract_f0_rmvpe.py \
        1 0 "${GPU_ID}" "${EXP_DIR}" "True"
else
    python infer/modules/train/extract/extract_f0_print.py \
        "${EXP_DIR}" \
        "${N_PROCS}" \
        "${F0_METHOD}"
fi

echo "F0 extraction complete."
echo ""

# Step 3: Extract features (Hubert)
echo "=== Step 3/5: Extracting Hubert features ==="
FEATURE_DIM="256"
[[ "$VERSION" == "v2" ]] && FEATURE_DIM="768"

python infer/modules/train/extract_feature_print.py \
    "cuda:${GPU_ID}" \
    1 0 "${GPU_ID}" \
    "${EXP_DIR}" \
    "${VERSION}" \
    "True"

echo "Feature extraction complete."
echo ""

# Step 4: Generate filelist
echo "=== Step 4/5: Generating filelist ==="
FILELIST="${EXP_DIR}/filelist.txt"
GT_DIR="${EXP_DIR}/0_gt_wavs"
FEAT_DIR="${EXP_DIR}/3_feature${FEATURE_DIM}"
F0_DIR="${EXP_DIR}/2a_f0"
F0NSF_DIR="${EXP_DIR}/2b-f0nsf"

# Find common files across all directories
python3 - <<PYTHON_SCRIPT
import os
gt_dir = "${GT_DIR}"
feat_dir = "${FEAT_DIR}"
f0_dir = "${F0_DIR}"
f0nsf_dir = "${F0NSF_DIR}"
filelist_path = "${FILELIST}"

gt_names = set(n.split('.')[0] for n in os.listdir(gt_dir) if n.endswith('.wav'))
feat_names = set(n.split('.')[0] for n in os.listdir(feat_dir) if n.endswith('.npy'))
f0_names = set(n.replace('.wav.npy', '') for n in os.listdir(f0_dir) if n.endswith('.npy'))
f0nsf_names = set(n.replace('.wav.npy', '') for n in os.listdir(f0nsf_dir) if n.endswith('.npy'))

common = gt_names & feat_names & f0_names & f0nsf_names
print(f"Found {len(common)} valid training samples")

with open(filelist_path, 'w') as f:
    for name in sorted(common):
        line = f"{gt_dir}/{name}.wav|{feat_dir}/{name}.npy|{f0_dir}/{name}.wav.npy|{f0nsf_dir}/{name}.wav.npy|0"
        f.write(line + "\n")

print(f"Wrote filelist to {filelist_path}")
PYTHON_SCRIPT

echo ""

# Step 5: Train
echo "=== Step 5/5: Training ==="
echo "This may take a while. Training for ${TOTAL_EPOCHS} epochs..."

# Check for pretrained models
if [[ ! -f "${PRETRAINED_G}" ]]; then
    echo "Warning: Pretrained generator not found at ${PRETRAINED_G}"
    echo "Training without pretrained model (will take longer)"
    PRETRAINED_G=""
fi

if [[ ! -f "${PRETRAINED_D}" ]]; then
    echo "Warning: Pretrained discriminator not found at ${PRETRAINED_D}"
    PRETRAINED_D=""
fi

python infer/modules/train/train.py \
    -e "${MODEL_NAME}" \
    -sr "${SAMPLE_RATE}" \
    -f0 1 \
    -bs "${BATCH_SIZE}" \
    -te "${TOTAL_EPOCHS}" \
    -se "${SAVE_EVERY}" \
    -pg "${PRETRAINED_G}" \
    -pd "${PRETRAINED_D}" \
    -l 0 \
    -c 0 \
    -sw 1 \
    -v "${VERSION}"

echo ""
echo "=== Training Complete ==="

# Step 6: Build Index
echo "=== Building retrieval index ==="
python tools/infer/train-index.py \
    "${EXP_DIR}" \
    "${VERSION}"

echo ""
echo "=== RVC Training Pipeline Complete ==="
echo ""
echo "Model saved to: ${EXP_DIR}"
echo "  - Weights: ${RVC_DIR}/assets/weights/${MODEL_NAME}.pth"
echo "  - Index:   ${EXP_DIR}/added_*.index"
echo ""
echo "To run inference:"
echo "  ./run.sh rvc-infer --model-name ${MODEL_NAME} --input INPUT.wav --output OUTPUT.wav"
