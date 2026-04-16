#!/usr/bin/env bash
# Sanity check for tts-horus skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Sanity check for tts-horus ==="

# Check SKILL.md exists
if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    exit 1
fi
echo "PASS: SKILL.md exists"

# Check python3 exists
if ! command -v python3 >/dev/null 2>&1; then
    echo "FAIL: python3 not found"
    exit 1
fi
echo "PASS: python3 found"

# Check ffmpeg exists (required for audio processing)
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "WARN: ffmpeg not found (required for audio processing)"
else
    echo "PASS: ffmpeg found"
fi

# Check whisperx is available
if python3 -c "import whisperx" 2>/dev/null; then
    echo "PASS: whisperx available"
else
    echo "WARN: whisperx not installed (required for alignment)"
fi

# Check torch is available
if python3 -c "import torch" 2>/dev/null; then
    echo "PASS: torch available"
else
    echo "WARN: torch not installed (required for TTS training)"
fi

echo "=== Sanity check complete ==="
