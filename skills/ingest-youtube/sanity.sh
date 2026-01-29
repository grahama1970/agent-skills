#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== YouTube Transcripts Sanity ==="

# Check required files exist
echo ""
echo "--- File Structure ---"
required_files=(
    "SKILL.md"
    "cli.py"
    "youtube_transcript.py"
    "youtube_transcript_monolith.py"
    "youtube_transcripts/__init__.py"
    "youtube_transcripts/config.py"
    "youtube_transcripts/utils.py"
    "youtube_transcripts/downloader.py"
    "youtube_transcripts/transcriber.py"
    "youtube_transcripts/formatter.py"
    "youtube_transcripts/batch.py"
)

all_exist=true
for file in "${required_files[@]}"; do
    if [[ -f "$SCRIPT_DIR/$file" ]]; then
        echo "  [PASS] $file exists"
    else
        echo "  [FAIL] $file missing"
        all_exist=false
    fi
done

if [[ "$all_exist" != "true" ]]; then
    echo "Result: FAIL (missing files)"
    exit 1
fi

# Check module line counts (quality gate: < 500 lines each)
echo ""
echo "--- Module Size Check (< 500 lines) ---"
modules=(
    "youtube_transcripts/config.py"
    "youtube_transcripts/utils.py"
    "youtube_transcripts/downloader.py"
    "youtube_transcripts/transcriber.py"
    "youtube_transcripts/formatter.py"
    "youtube_transcripts/batch.py"
    "cli.py"
)

size_ok=true
for mod in "${modules[@]}"; do
    lines=$(wc -l < "$SCRIPT_DIR/$mod")
    if [[ $lines -lt 500 ]]; then
        echo "  [PASS] $mod: $lines lines"
    else
        echo "  [FAIL] $mod: $lines lines (exceeds 500)"
        size_ok=false
    fi
done

if [[ "$size_ok" != "true" ]]; then
    echo "Result: FAIL (module too large)"
    exit 1
fi

# Check Python syntax for all modules
echo ""
echo "--- Syntax Check ---"
syntax_ok=true
py_files=(
    "cli.py"
    "youtube_transcript.py"
    "youtube_transcripts/__init__.py"
    "youtube_transcripts/config.py"
    "youtube_transcripts/utils.py"
    "youtube_transcripts/downloader.py"
    "youtube_transcripts/transcriber.py"
    "youtube_transcripts/formatter.py"
    "youtube_transcripts/batch.py"
)

for pyfile in "${py_files[@]}"; do
    if python3 -m py_compile "$SCRIPT_DIR/$pyfile" 2>/dev/null; then
        echo "  [PASS] $pyfile syntax OK"
    else
        echo "  [FAIL] $pyfile syntax error"
        syntax_ok=false
    fi
done

if [[ "$syntax_ok" != "true" ]]; then
    echo "Result: FAIL (syntax errors)"
    exit 1
fi

# Check for circular imports by attempting to import the package
echo ""
echo "--- Import Check ---"
if python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from youtube_transcripts import config
from youtube_transcripts import utils
from youtube_transcripts import downloader
from youtube_transcripts import transcriber
from youtube_transcripts import formatter
from youtube_transcripts import batch
print('  All modules import successfully')
" 2>&1; then
    echo "  [PASS] No circular imports detected"
else
    echo "  [FAIL] Import error (possible circular import)"
    exit 1
fi

# Check CLI can be invoked (help)
echo ""
echo "--- CLI Invocation Check ---"
if python3 "$SCRIPT_DIR/cli.py" --help >/dev/null 2>&1; then
    echo "  [PASS] CLI --help works"
else
    echo "  [FAIL] CLI --help failed"
    exit 1
fi

# Check entry point wrapper
if python3 "$SCRIPT_DIR/youtube_transcript.py" --help >/dev/null 2>&1; then
    echo "  [PASS] youtube_transcript.py --help works"
else
    echo "  [FAIL] youtube_transcript.py --help failed"
    exit 1
fi

echo ""
echo "=== Result: PASS ==="
