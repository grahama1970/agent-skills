#!/bin/bash
# Sanity script: FFmpeg concat filter
# Purpose: Verify FFmpeg can concatenate images into video
# Exit codes: 0=PASS, 1=FAIL, 42=CLARIFY

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_DIR="$SCRIPT_DIR/fixtures"

# Check ffmpeg exists
if ! command -v ffmpeg &> /dev/null; then
    echo "FAIL: ffmpeg not installed"
    exit 1
fi

# Check ffprobe exists
if ! command -v ffprobe &> /dev/null; then
    echo "FAIL: ffprobe not installed"
    exit 1
fi

# Create test images if needed
mkdir -p "$FIXTURE_DIR"
if [ ! -f "$FIXTURE_DIR/frame1.png" ]; then
    # Create simple test frames using ImageMagick or Python
    python3 -c "
from PIL import Image, ImageDraw
for i in range(3):
    img = Image.new('RGB', (640, 480), color=(50 + i*50, 100, 150))
    d = ImageDraw.Draw(img)
    d.text((280, 220), f'Frame {i+1}', fill=(255, 255, 255))
    img.save('$FIXTURE_DIR/frame{}.png'.format(i+1))
print('Created test frames')
"
fi

# Create concat input file
cat > "$FIXTURE_DIR/concat.txt" << EOF
file 'frame1.png'
duration 1
file 'frame2.png'
duration 1
file 'frame3.png'
duration 1
EOF

# Test concat
OUTPUT="$FIXTURE_DIR/test_output.mp4"
rm -f "$OUTPUT"

ffmpeg -y -f concat -safe 0 -i "$FIXTURE_DIR/concat.txt" \
    -vf "fps=24,format=yuv420p" \
    -c:v libx264 -preset ultrafast \
    "$OUTPUT" 2>/dev/null

if [ -f "$OUTPUT" ]; then
    # Verify with ffprobe
    DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUTPUT" 2>/dev/null)
    if [ -n "$DURATION" ]; then
        echo "PASS: Created video, duration=${DURATION}s"
        rm -f "$OUTPUT" "$FIXTURE_DIR/concat.txt"
        exit 0
    fi
fi

echo "FAIL: Could not create valid video"
exit 1
