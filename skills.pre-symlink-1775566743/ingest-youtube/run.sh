#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# YouTube Transcripts - Extract transcripts from YouTube videos
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env from skill directory (IPRoyal proxy config)
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a  # Export all variables
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Also check project root .env for fallback
PROJECT_ROOT="${SCRIPT_DIR%/.pi/*}"
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# If first arg is a URL, extract video ID and get transcript
if [[ "${1:-}" =~ youtube\.com|youtu\.be ]]; then
    # Extract video ID from URL
    url="$1"
    if [[ "$url" =~ v=([a-zA-Z0-9_-]+) ]]; then
        video_id="${BASH_REMATCH[1]}"
    elif [[ "$url" =~ youtu\.be/([a-zA-Z0-9_-]+) ]]; then
        video_id="${BASH_REMATCH[1]}"
    else
        echo "Could not extract video ID from: $url" >&2
        exit 1
    fi
    exec uv run --directory "$SCRIPT_DIR" python youtube_transcript.py get -i "$video_id"
else
    # Pass through to python script
    exec uv run --directory "$SCRIPT_DIR" python youtube_transcript.py "$@"
fi
