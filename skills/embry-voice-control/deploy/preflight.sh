#!/usr/bin/env bash
set -euo pipefail

: "${REALTIMESTT_REPO:?set REALTIMESTT_REPO}"
: "${CHATTERBOX_REPO:?set CHATTERBOX_REPO}"
: "${EMBRY_AUDIO_RUNTIME_DIR:?set EMBRY_AUDIO_RUNTIME_DIR}"
: "${EMBRY_OPENWAKEWORD_MODEL_DIR:?set EMBRY_OPENWAKEWORD_MODEL_DIR}"
: "${EMBRY_REF_AUDIO:?set EMBRY_REF_AUDIO}"
: "${HF_HOME:?set HF_HOME}"

command -v docker >/dev/null
command -v pw-record >/dev/null
docker compose version >/dev/null
nvidia-smi --query-gpu=name --format=csv,noheader >/dev/null
test -d "$REALTIMESTT_REPO/.git"
test -d "$CHATTERBOX_REPO/.git"
mkdir -p "$EMBRY_AUDIO_RUNTIME_DIR"
chmod 700 "$EMBRY_AUDIO_RUNTIME_DIR"
test -r "$EMBRY_OPENWAKEWORD_MODEL_DIR/hey_embry.onnx"
test -r "$EMBRY_REF_AUDIO"
test -d "$HF_HOME"

echo "embry-container-preflight-pass"
