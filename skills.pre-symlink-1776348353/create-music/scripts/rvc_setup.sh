#!/usr/bin/env bash
#
# RVC Setup Script
# Clone repo + download pretrained models
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
RVC_DIR="${SKILL_DIR}/rvc"

echo "=== RVC Setup ==="

# Clone RVC repo if not exists
if [[ ! -d "${RVC_DIR}" ]]; then
    echo "Cloning RVC WebUI repo..."
    git clone --depth 1 https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git "${RVC_DIR}"
else
    echo "RVC repo already exists at ${RVC_DIR}"
fi

cd "${RVC_DIR}"

# Create pretrained directories
mkdir -p pretrained_v2
mkdir -p assets/hubert

# Download pretrained models
echo "Downloading pretrained models..."

# f0 predictor models
PRETRAINED_FILES=(
    "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/rmvpe.pt"
    "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/hubert_base.pt"
)

for url in "${PRETRAINED_FILES[@]}"; do
    filename=$(basename "$url")
    if [[ ! -f "assets/${filename}" ]] && [[ ! -f "assets/hubert/${filename}" ]]; then
        echo "  Downloading ${filename}..."
        wget -q -P assets/ "${url}" || curl -sL "${url}" -o "assets/${filename}"
    else
        echo "  ${filename} already exists"
    fi
done

# Move hubert to correct location
if [[ -f "assets/hubert_base.pt" ]]; then
    mv assets/hubert_base.pt assets/hubert/
fi

# Install requirements (in skill venv)
echo "Installing RVC requirements..."
if [[ -f requirements.txt ]]; then
    pip install -r requirements.txt --quiet 2>/dev/null || echo "Some requirements may have failed"
fi

echo ""
echo "=== RVC Setup Complete ==="
echo "RVC directory: ${RVC_DIR}"
echo ""
echo "To run inference:"
echo "  ./run.sh rvc-infer --model-name MODEL --input INPUT.wav --output OUTPUT.wav"
