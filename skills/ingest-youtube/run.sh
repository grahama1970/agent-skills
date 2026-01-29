#!/usr/bin/env bash
# YouTube Transcripts - Extract transcripts from YouTube videos
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
