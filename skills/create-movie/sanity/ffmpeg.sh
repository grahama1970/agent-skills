#!/usr/bin/env bash
#
# Sanity script: FFmpeg availability
# Purpose: Verify FFmpeg is available for video processing
# Exit codes: 0=PASS, 1=FAIL
#
set -e

echo "Checking FFmpeg availability..."

# Check ffmpeg command exists
if ! command -v ffmpeg &> /dev/null; then
    echo "FAIL: FFmpeg not installed. Install with: apt install ffmpeg"
    exit 1
fi

# Check version
VERSION=$(ffmpeg -version 2>&1 | head -1)
echo "Found: $VERSION"

# Test basic functionality - create a test frame
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

# Create a simple test video (1 second of black)
if ! ffmpeg -f lavfi -i color=black:s=320x240:d=1 -c:v libx264 -t 1 "$TMPDIR/test.mp4" -y &> /dev/null; then
    echo "FAIL: FFmpeg cannot create video"
    exit 1
fi

# Check the output file exists and has content
if [[ ! -s "$TMPDIR/test.mp4" ]]; then
    echo "FAIL: FFmpeg output file is empty"
    exit 1
fi

echo "PASS: FFmpeg is available and working"
exit 0
