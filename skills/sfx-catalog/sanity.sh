#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== sfx-catalog Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh pyproject.toml src/__init__.py src/cli.py src/audio_analyzer.py src/content_classifier.py src/memory_bridge.py src/query_engine.py src/metadata_generator.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: $f missing"
        exit 1
    fi
done
echo "OK"

# Check 2: run.sh is executable
echo -n "Check 2: run.sh executable... "
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh not executable"
    exit 1
fi
echo "OK"

# Check 3: uv available
echo -n "Check 3: uv available... "
if ! command -v uv >/dev/null 2>&1; then
    echo "FAIL: uv not found"
    exit 1
fi
echo "OK"

# Check 4: Virtual environment exists
echo -n "Check 4: Virtual environment... "
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    echo "FAIL: .venv not found. Run 'cd $SCRIPT_DIR && uv sync'"
    exit 1
fi
echo "OK"

# Check 5: Core Python deps importable via venv
echo -n "Check 5: Python dependencies... "
if ! "$SCRIPT_DIR/.venv/bin/python" -c "import typer; import rich; import numpy" 2>/dev/null; then
    echo "FAIL: Missing core deps (typer, rich, numpy)"
    echo "  Run: cd $SCRIPT_DIR && uv sync"
    exit 1
fi
echo "OK"

# Check 6: librosa importable (audio analysis)
echo -n "Check 6: librosa... "
if ! "$SCRIPT_DIR/.venv/bin/python" -c "import librosa" 2>/dev/null; then
    echo "FAIL: librosa not installed"
    echo "  Run: cd $SCRIPT_DIR && uv sync"
    exit 1
fi
echo "OK"

# Check 7: soundfile importable
echo -n "Check 7: soundfile... "
if ! "$SCRIPT_DIR/.venv/bin/python" -c "import soundfile" 2>/dev/null; then
    echo "FAIL: soundfile not installed"
    echo "  Run: cd $SCRIPT_DIR && uv sync"
    exit 1
fi
echo "OK"

# Check 8: CLI module loadable
echo -n "Check 8: CLI module... "
if ! "$SCRIPT_DIR/.venv/bin/python" -c "from src.cli import app" 2>/dev/null; then
    echo "FAIL: src.cli module broken"
    exit 1
fi
echo "OK"

# Check 9: SFX data directory
echo -n "Check 9: Data directory... "
SFX_DATA_DIR="${SFX_DATA_DIR:-$HOME/.pi/sfx-catalog}"
mkdir -p "$SFX_DATA_DIR" 2>/dev/null
if [[ ! -w "$SFX_DATA_DIR" ]]; then
    echo "FAIL: $SFX_DATA_DIR not writable"
    exit 1
fi
echo "OK ($SFX_DATA_DIR)"

# Check 10: SFX library path exists (optional)
echo -n "Check 10: SFX library... "
SFX_LIB="/mnt/storage12tb/media/sfx"
if [[ -d "$SFX_LIB" ]]; then
    COUNT=$(find "$SFX_LIB" -maxdepth 1 -name "*.mp3" 2>/dev/null | wc -l)
    echo "OK ($COUNT MP3 files at $SFX_LIB)"
else
    echo "SKIP (SFX library not found at $SFX_LIB)"
fi

echo "Result: PASS"
