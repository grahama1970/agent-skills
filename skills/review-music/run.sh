#!/usr/bin/env bash
# review-music skill runner
#
# Commands:
#   analyze <audio_file>     - Extract all features and generate analysis
#   features <audio_file>    - Extract specific audio features
#   review <audio_file>      - Generate full HMT-mapped review
#   batch <directory>        - Batch analyze all audio files
#
# Examples:
#   ./run.sh analyze song.mp3
#   ./run.sh features song.mp3 --bpm --key
#   ./run.sh review song.mp3 --sync-memory
#   ./run.sh batch ./music_folder --output reviews.jsonl

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Prefer local .venv if it exists (avoids Python version conflicts)
if [[ -f ".venv/bin/python" ]]; then
    PYTHON=".venv/bin/python"
elif command -v uv &> /dev/null; then
    PYTHON="uv run python"
else
    PYTHON="python3"
fi

show_help() {
    cat << 'EOF'
review-music - Audio analysis with MIR tools + LLM music theory reasoning

USAGE:
    ./run.sh <command> [options]

COMMANDS:
    analyze <audio_file>     Extract all features and generate analysis
    features <audio_file>    Extract specific audio features only
    review <audio_file>      Generate full HMT-mapped review
    batch <directory>        Batch analyze all audio files

OPTIONS:
    --youtube <url>          Download and analyze from YouTube URL
    --output <file>          Output JSON file (default: stdout)
    --no-lyrics              Skip lyrics transcription
    --no-llm                 Skip LLM analysis, features only
    --sync-memory            Sync to /memory after review
    --bpm                    Extract BPM only
    --key                    Extract key only
    --chords                 Extract chords only
    --timbre                 Extract timbre features only
    --dynamics               Extract dynamics only

EXAMPLES:
    ./run.sh analyze song.mp3
    ./run.sh analyze --youtube "https://youtube.com/watch?v=dQw4w9WgXcQ"
    ./run.sh features song.mp3 --bpm --key
    ./run.sh review song.mp3 --sync-memory
    ./run.sh batch ./music --output reviews.jsonl

EOF
}

cmd_analyze() {
    echo -e "${GREEN}Analyzing audio...${NC}"
    $PYTHON -m src.cli analyze "$@"
}

cmd_features() {
    echo -e "${GREEN}Extracting features...${NC}"
    $PYTHON -m src.cli features "$@"
}

cmd_review() {
    echo -e "${GREEN}Generating review...${NC}"
    $PYTHON -m src.cli review "$@"
}

cmd_batch() {
    echo -e "${GREEN}Batch processing...${NC}"
    $PYTHON -m src.cli batch "$@"
}

# Main command dispatcher
case "${1:-help}" in
    analyze)
        shift
        cmd_analyze "$@"
        ;;
    features)
        shift
        cmd_features "$@"
        ;;
    review)
        shift
        cmd_review "$@"
        ;;
    batch)
        shift
        cmd_batch "$@"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        show_help
        exit 1
        ;;
esac
