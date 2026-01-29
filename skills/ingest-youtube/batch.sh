#!/bin/bash
# Batch YouTube transcript downloader with IPRoyal proxy and exponential backoff
# Usage: ./batch.sh <input_file> <output_dir> [delay_min] [delay_max]
#
# Examples:
#   ./batch.sh videos.txt ./transcripts              # Default 5-10 min delays
#   ./batch.sh videos.txt ./transcripts 300 600      # 5-10 min delays
#   ./batch.sh videos.txt ./transcripts 600 900      # 10-15 min delays (safer)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_DIR="$(pwd)"

INPUT_ARG="${1:?Usage: batch.sh <input_file> <output_dir> [delay_min] [delay_max]}"
OUTPUT_ARG="${2:?Usage: batch.sh <input_file> <output_dir> [delay_min] [delay_max]}"
DELAY_MIN="${3:-300}"   # Default 5 minutes
DELAY_MAX="${4:-600}"   # Default 10 minutes

# Convert relative paths to absolute (based on starting directory)
if [[ "$INPUT_ARG" = /* ]]; then
    INPUT_FILE="$INPUT_ARG"
else
    INPUT_FILE="$START_DIR/$INPUT_ARG"
fi

if [[ "$OUTPUT_ARG" = /* ]]; then
    OUTPUT_DIR="$OUTPUT_ARG"
else
    OUTPUT_DIR="$START_DIR/$OUTPUT_ARG"
fi

if [[ ! -f "$INPUT_FILE" ]]; then
    echo "Error: Input file not found: $INPUT_FILE"
    exit 1
fi

echo "=== YouTube Batch Transcriber (IPRoyal + Backoff) ==="
echo "Input:     $INPUT_FILE"
echo "Output:    $OUTPUT_DIR"
echo "Delay:     ${DELAY_MIN}-${DELAY_MAX}s between requests"
echo "Backoff:   60-900s exponential on rate limits"
echo ""

# Ensure venv exists and dependencies installed
cd "$SCRIPT_DIR"

# Load IPRoyal proxy credentials from .env
if [[ -f ".env" ]]; then
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
        # Remove any quotes from value
        value="${value%\"}"
        value="${value#\"}"
        export "$key=$value"
    done < .env
    echo "Loaded proxy config (IPROYAL_HOST=$IPROYAL_HOST)"
fi

# Use full path to uv (needed for scheduler/cron environments)
UV="${UV:-/home/graham/.local/bin/uv}"
if [[ ! -x "$UV" ]]; then
    UV="$(which uv 2>/dev/null || echo "uv")"
fi

"$UV" sync --quiet 2>/dev/null || true

# Run the batch command with IPRoyal proxy (default) and exponential backoff
# --whisper enables Whisper fallback for videos without captions (requires OPENAI_API_KEY)
"$UV" run python youtube_transcript.py batch \
    --input "$INPUT_FILE" \
    --output "$OUTPUT_DIR" \
    --delay-min "$DELAY_MIN" \
    --delay-max "$DELAY_MAX" \
    --backoff-base 60 \
    --backoff-max 900 \
    --whisper \
    --resume
