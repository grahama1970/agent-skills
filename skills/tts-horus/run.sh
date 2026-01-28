#!/usr/bin/env bash
# Entry point for the tts-horus skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<EOF
tts-horus: Build and operate the Horus TTS pipeline from cleared audiobooks.

Commands:
  dataset          Build the Horus dataset from audiobook (transcribe, segment, extract clips)
  align            Run WhisperX alignment with lexicon overrides
  train            Fine-tune XTTS-v2 using GPTTrainer
  say              CLI synthesis (writes output.wav by default)
  server           FastAPI server for low-latency synthesis
  color            Voice coloring helper (modify timbre/emotion)

Environment:
  Project root should contain:
    - run/tts/*.py (implementation scripts)
    - configs/tts/*.yaml (training configs)
    - persona/data/audiobooks/ (audiobook data)
    - datasets/horus_voice/ (extracted clips and manifests)

Examples:
  ./run.sh dataset
  ./run.sh align
  ./run.sh train
  ./run.sh say "Lupercal speaks."
  ./run.sh server
  ./run.sh color --base horus --color warm --alpha 0.4

For more info, see: $SCRIPT_DIR/SKILL.md
EOF
}

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

CMD="$1"
shift

case "$CMD" in
    dataset)
        # Run dataset preparation pipeline
        echo "Building Horus dataset..."
        python3 "${SCRIPT_DIR}/../../../run/tts/ingest_audiobook.py" "$@"
        ;;
    align)
        # Run WhisperX alignment
        echo "Running WhisperX alignment..."
        python3 "${SCRIPT_DIR}/../../../run/tts/align_transcripts.py" "$@"
        ;;
    train)
        # Fine-tune XTTS-v2
        echo "Starting XTTS-v2 training..."
        python3 "${SCRIPT_DIR}/../../../run/tts/train_xtts_coqui.py" "$@"
        ;;
    say)
        # CLI synthesis
        echo "Synthesizing speech..."
        python3 "${SCRIPT_DIR}/../../../run/tts/say.py" "$@"
        ;;
    server)
        # FastAPI synthesis server
        echo "Starting TTS synthesis server..."
        python3 "${SCRIPT_DIR}/../../../run/tts/server.py" "$@"
        ;;
    color)
        # Voice coloring helper
        echo "Applying voice coloring..."
        python3 "${SCRIPT_DIR}/../../../run/tts/color_voice.py" "$@"
        ;;
    -h|--help|help)
        usage
        exit 0
        ;;
    *)
        echo "Unknown command: $CMD" >&2
        usage
        exit 1
        ;;
esac
