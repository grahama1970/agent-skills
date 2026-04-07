#!/usr/bin/env bash
# Sanity check for review-design skill
#
# Verifies:
# 1. Python files are syntactically valid
# 2. Required dependencies are available
# 3. At least one vision provider CLI is accessible
# 4. Output directory is writable

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== review-design sanity check ==="
echo

# Check Python syntax
echo "[1/5] Checking Python syntax..."
python3 -m py_compile config.py
python3 -m py_compile prompts.py
python3 -m py_compile review_design.py
echo "    ✓ All Python files are valid"

# Check imports
echo "[2/5] Checking Python imports..."
python3 -c "from config import PROVIDERS, ReviewRequest" 2>/dev/null && echo "    ✓ config.py imports work" || { echo "    ✗ config.py import failed"; exit 1; }
python3 -c "from prompts import SYSTEM_PROMPT, format_step1_prompt" 2>/dev/null && echo "    ✓ prompts.py imports work" || { echo "    ✗ prompts.py import failed"; exit 1; }

# Check for vision provider CLIs
echo "[3/5] Checking vision provider CLIs..."
FOUND_PROVIDER=0

if command -v claude &> /dev/null; then
    echo "    ✓ claude CLI found: $(which claude)"
    FOUND_PROVIDER=1
else
    echo "    - claude CLI not found"
fi

if command -v openai &> /dev/null; then
    echo "    ✓ openai CLI found: $(which openai)"
    FOUND_PROVIDER=1
else
    echo "    - openai CLI not found"
fi

if command -v gemini &> /dev/null; then
    echo "    ✓ gemini CLI found: $(which gemini)"
    FOUND_PROVIDER=1
else
    echo "    - gemini CLI not found"
fi

if [[ $FOUND_PROVIDER -eq 0 ]]; then
    echo "    ⚠ Warning: No vision provider CLI found"
    echo "      Install one of: claude, openai, gemini"
fi

# Check output directory
echo "[4/5] Checking output directory..."
OUTPUT_DIR="$SCRIPT_DIR/review_output"
if [[ -d "$OUTPUT_DIR" ]]; then
    echo "    ✓ Output directory exists: $OUTPUT_DIR"
else
    mkdir -p "$OUTPUT_DIR"
    echo "    ✓ Output directory created: $OUTPUT_DIR"
fi

if [[ -w "$OUTPUT_DIR" ]]; then
    echo "    ✓ Output directory is writable"
else
    echo "    ✗ Output directory is not writable"
    exit 1
fi

# Check optional PIL dependency
echo "[5/5] Checking optional dependencies..."
if python3 -c "from PIL import Image" 2>/dev/null; then
    echo "    ✓ PIL/Pillow available (image resizing enabled)"
else
    echo "    - PIL/Pillow not available (images won't be auto-resized)"
fi

echo
echo "=== Sanity check passed ==="
echo
echo "Usage:"
echo "  ./run.sh review --screenshots ./ui/ --tokens ./tokens.json"
echo "  ./run.sh check --provider claude"
