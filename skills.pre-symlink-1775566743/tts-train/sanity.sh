#!/usr/bin/env bash
# Sanity check for tts-train skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Sanity check for tts-train ==="

# Check python3 exists
if ! command -v python3 >/dev/null 2>&1; then
    echo "FAIL: python3 not found"
    exit 1
fi
echo "PASS: python3 found"

# Check main CLI script exists
if [[ ! -f "$SCRIPT_DIR/cli.py" ]]; then
    echo "FAIL: cli.py not found"
    exit 1
fi
echo "PASS: cli.py exists"

# Check run.sh exists and is executable
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "WARN: run.sh not found or not executable"
else
    echo "PASS: run.sh exists and is executable"
fi

# Check SKILL.md exists
if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    exit 1
fi
echo "PASS: SKILL.md exists"

# Check CLI help works
if python3 "$SCRIPT_DIR/cli.py" --help >/dev/null 2>&1; then
    echo "PASS: CLI --help works"
else
    echo "WARN: CLI --help check failed (may need dependencies)"
fi

# Check ffmpeg exists (required for audio processing)
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "WARN: ffmpeg not found (required for audio processing)"
else
    echo "PASS: ffmpeg found"
fi

# Check torch is available
if python3 -c "import torch" 2>/dev/null; then
    echo "PASS: torch available"
else
    echo "WARN: torch not installed (required for TTS training)"
fi

echo "=== Sanity check complete ==="
