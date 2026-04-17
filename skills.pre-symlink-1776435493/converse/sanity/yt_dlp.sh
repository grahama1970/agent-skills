#!/usr/bin/env bash
# Sanity check: yt-dlp can download audio from YouTube
set -euo pipefail

echo "=== yt-dlp Sanity Check ==="

# Check 1: yt-dlp installed
echo -n "  [1/3] yt-dlp binary: "
if command -v yt-dlp &>/dev/null; then
    echo "PASS ($(yt-dlp --version))"
else
    echo "FAIL: yt-dlp not found"
    echo "  Install: pip install yt-dlp"
    exit 1
fi

# Check 2: ffmpeg (required for audio extraction)
echo -n "  [2/3] ffmpeg: "
if command -v ffmpeg &>/dev/null; then
    echo "PASS"
else
    echo "FAIL: ffmpeg not found"
    exit 1
fi

# Check 3: Download 10s of a short public domain test clip
# Uses Hawaiian War Chant (target track) with --download-sections to limit
echo -n "  [3/3] Download test (10s audio): "
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

if yt-dlp \
    --extract-audio \
    --audio-format wav \
    --download-sections "*0:00-0:10" \
    --output "${TMPDIR}/test.%(ext)s" \
    --no-playlist \
    --quiet \
    "https://youtu.be/Dordpe3KX_I" 2>/dev/null; then

    WAV=$(find "${TMPDIR}" -name "*.wav" | head -1)
    if [[ -n "$WAV" ]] && [[ -f "$WAV" ]]; then
        SIZE=$(stat -c%s "$WAV" 2>/dev/null || stat -f%z "$WAV" 2>/dev/null)
        if [[ "$SIZE" -gt 10000 ]]; then
            echo "PASS (${SIZE} bytes)"
        else
            echo "FAIL: Downloaded file too small (${SIZE} bytes)"
            exit 1
        fi
    else
        echo "FAIL: No WAV file produced"
        exit 1
    fi
else
    echo "FAIL: yt-dlp download failed"
    exit 1
fi

echo "=== yt-dlp: PASS ==="
