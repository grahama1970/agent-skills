#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
#
# create-music Skill Runner
# AI-assisted music creation for Horus persona
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

usage() {
    cat <<EOF
Usage: ./run.sh <command> [options]

Commands:
  separate --mix FILE --out DIR     Stem separation (Demucs/UVR)
  qc-select --mix FILE --candidates DIR --out DIR
                                    QC select best stems from ensemble
  rvc-setup                         One-time RVC repo + pretrain setup
  rvc-train --name NAME --input-dir DIR [--epochs N] [--sample-rate SR]
                                    Train a new voice model
  rvc-infer --model-name NAME --input FILE --output FILE [--pitch N] [--f0method METHOD]
                                    Voice conversion inference
  musicgen --prompt TEXT --seconds N --out FILE [--model MODEL]
                                    Generate music with MusicGen (runs in Docker)
  musicgen-build                    Build the MusicGen Docker image
  yue --lyrics FILE --genre TAGS --out DIR [--quantization int8] [--stage1-only]
                                    Generate music with YuE (runs in Docker, GPU)
  yue-build                         Build the YuE Docker image
  yue-stage1 --lyrics FILE --genre TAGS --out DIR
                                    Run YuE Stage 1 only (symbolic tokens as JSON)
  midi-from-spec --spec FILE --out FILE
                                    Convert piano-roll-spec.json → MIDI file
  midi-to-spec --midi FILE --out FILE Convert MIDI file → piano-roll-spec.json
  sonauto --prompt TEXT --out FILE [--tags rock,jazz] [--lyrics TEXT]
                                    Generate music via Sonauto cloud API (lyrics-aware)
  sonauto-extend --audio FILE --out FILE --prompt TEXT [--side right] [--duration 30]
                                    Extend song from start or end (0-85s, v2)
  sonauto-inpaint --audio FILE --out FILE --start N --end N --lyrics TEXT
                                    Replace a section with new content (v2)
  sonauto-status --task-id ID      Check task status, optionally download
  sonauto-credits                   Check Sonauto API credit balance

Options:
  --help                            Show this help message
  --with-audio-separator            Include UVR models in ensemble (separate)
  --model MODEL                     Demucs model (htdemucs, htdemucs_ft, etc.)

Examples:
  ./run.sh separate --mix song.wav --out work/stems --model htdemucs
  ./run.sh rvc-infer --model-name nico-500 --input vocals.wav --output converted.wav --pitch 0
  ./run.sh musicgen --checkpoint-dir ./checkpoints/jazz --prompt "soft piano trio" --seconds 30 --out out.wav
EOF
}

# Ensure venv exists
ensure_venv() {
    if [[ ! -d "${SCRIPT_DIR}/.venv" ]]; then
        echo "[create-music] Creating virtual environment..."
        uv venv "${SCRIPT_DIR}/.venv"
        uv pip install -r "${SCRIPT_DIR}/requirements.txt" --quiet
    fi
}

# Parse command
COMMAND="${1:-help}"
shift || true

MUSICGEN_IMAGE="create-music-musicgen:latest"
YUE_IMAGE="create-music-yue:latest"

case "$COMMAND" in
    separate|qc-select|ingest-raw)
        ensure_venv
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/cli.py" "$COMMAND" "$@"
        ;;
    musicgen-build)
        echo "[create-music] Building MusicGen Docker image..."
        docker build -t "${MUSICGEN_IMAGE}" -f "${SCRIPT_DIR}/docker/Dockerfile.musicgen" "${SCRIPT_DIR}/docker"
        echo "[create-music] Image built: ${MUSICGEN_IMAGE}"
        ;;
    musicgen)
        # Check if Docker image exists
        if ! docker image inspect "${MUSICGEN_IMAGE}" &>/dev/null; then
            echo "[create-music] MusicGen image not found. Building..."
            docker build -t "${MUSICGEN_IMAGE}" -f "${SCRIPT_DIR}/docker/Dockerfile.musicgen" "${SCRIPT_DIR}/docker"
        fi
        # Run MusicGen in Docker with GPU support
        # Convert relative paths to absolute for Docker mount
        DOCKER_ARGS=()
        OUT_DIR=""
        CHECKPOINT_DIR=""
        while [[ $# -gt 0 ]]; do
            case $1 in
                --out|-o)
                    OUT_PATH="$(realpath -m "$2")"
                    OUT_DIR="$(dirname "$OUT_PATH")"
                    DOCKER_ARGS+=("--out" "/output/$(basename "$OUT_PATH")")
                    shift 2
                    ;;
                --checkpoint-dir|-c)
                    CHECKPOINT_DIR="$(realpath "$2")"
                    DOCKER_ARGS+=("--checkpoint-dir" "/checkpoint")
                    shift 2
                    ;;
                *)
                    DOCKER_ARGS+=("$1")
                    shift
                    ;;
            esac
        done
        # Build docker run command
        DOCKER_CMD=(docker run --rm --gpus all)
        [[ -n "$OUT_DIR" ]] && DOCKER_CMD+=(-v "${OUT_DIR}:/output")
        [[ -n "$CHECKPOINT_DIR" ]] && DOCKER_CMD+=(-v "${CHECKPOINT_DIR}:/checkpoint:ro")
        DOCKER_CMD+=("${MUSICGEN_IMAGE}" "${DOCKER_ARGS[@]}")
        exec "${DOCKER_CMD[@]}"
        ;;
    yue-build)
        echo "[create-music] Building YuE Docker image..."
        docker build -t "${YUE_IMAGE}" -f "${SCRIPT_DIR}/docker/Dockerfile.yue" "${SCRIPT_DIR}/docker"
        echo "[create-music] Image built: ${YUE_IMAGE}"
        ;;
    yue|yue-stage1)
        if ! docker image inspect "${YUE_IMAGE}" &>/dev/null; then
            echo "[create-music] YuE image not found. Building (this takes ~15 min first time)..."
            docker build -t "${YUE_IMAGE}" -f "${SCRIPT_DIR}/docker/Dockerfile.yue" "${SCRIPT_DIR}/docker"
        fi
        YUE_ARGS=("generate")
        [[ "$COMMAND" == "yue-stage1" ]] && YUE_ARGS+=("--stage1-only")
        INPUT_DIR="" OUT_DIR="" MODELS_DIR="/mnt/storage12tb/models/huggingface"
        while [[ $# -gt 0 ]]; do
            case $1 in
                --lyrics)
                    LYRICS_PATH="$(realpath "$2")"
                    INPUT_DIR="$(dirname "$LYRICS_PATH")"
                    YUE_ARGS+=("--lyrics" "/input/$(basename "$LYRICS_PATH")")
                    shift 2 ;;
                --out)
                    OUT_DIR="$(realpath -m "$2")"
                    mkdir -p "$OUT_DIR"
                    YUE_ARGS+=("--out" "/output")
                    shift 2 ;;
                *)
                    YUE_ARGS+=("$1")
                    shift ;;
            esac
        done
        DOCKER_CMD=(docker run --rm --gpus all)
        [[ -n "$INPUT_DIR" ]] && DOCKER_CMD+=(-v "${INPUT_DIR}:/input:ro")
        [[ -n "$OUT_DIR" ]] && DOCKER_CMD+=(-v "${OUT_DIR}:/output")
        DOCKER_CMD+=(-v "${MODELS_DIR}:/models/huggingface")
        DOCKER_CMD+=("${YUE_IMAGE}" "${YUE_ARGS[@]}")
        exec "${DOCKER_CMD[@]}"
        ;;
    midi-from-spec)
        ensure_venv
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/midi_utils.py" from-spec "$@"
        ;;
    midi-to-spec)
        ensure_venv
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/midi_utils.py" to-spec "$@"
        ;;
    rvc-setup)
        exec bash "${SCRIPT_DIR}/scripts/rvc_setup.sh" "$@"
        ;;
    rvc-train)
        exec bash "${SCRIPT_DIR}/scripts/rvc_train.sh" "$@"
        ;;
    rvc-infer)
        exec bash "${SCRIPT_DIR}/scripts/rvc_infer.sh" "$@"
        ;;
    sonauto)
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/sonauto.py" generate "$@"
        ;;
    sonauto-extend)
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/sonauto.py" extend "$@"
        ;;
    sonauto-inpaint)
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/sonauto.py" inpaint "$@"
        ;;
    sonauto-status)
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/sonauto.py" status "$@"
        ;;
    sonauto-credits)
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/sonauto.py" credits "$@"
        ;;
    sanity)
        exec bash "${SCRIPT_DIR}/sanity.sh" "$@"
        ;;
    help|--help|-h)
        usage
        exit 0
        ;;
    *)
        echo "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
