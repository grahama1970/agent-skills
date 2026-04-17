#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [train-voice] Sanity Check ==="

# Check 1: Required files exist
echo "Check 1: Required files..."
for f in SKILL.md run.sh train.py design.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: Missing $f"
        exit 1
    fi
done
echo "  All required files present"

# Check 2: run.sh is executable
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh is not executable"
    exit 1
fi
echo "  run.sh is executable"

# Check 3: uv available
if ! command -v uv &>/dev/null; then
    echo "FAIL: uv not found"
    exit 1
fi
echo "  uv available"

# Check 4: Python imports
if python3 -c "
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress
" 2>/dev/null; then
    echo "  Python imports OK (typer, rich)"
else
    echo "FAIL: Python imports failed (typer, rich)"
    exit 1
fi

if python3 -c "import yaml" 2>/dev/null; then
    echo "  pyyaml available"
else
    echo "  WARN: pyyaml not installed (needed for persona YAML loading)"
fi

# Check 5: Python files are parseable
for pyfile in train.py design.py; do
    if ! python3 -c "import ast; ast.parse(open('$SCRIPT_DIR/$pyfile').read())" 2>/dev/null; then
        echo "FAIL: $pyfile has syntax errors"
        exit 1
    fi
done
echo "  Python files parse without errors"

# Check 6: help command works
help_output=$("$SCRIPT_DIR/run.sh" help 2>&1 || true)
if echo "$help_output" | grep -qi "train-voice\|unified voice"; then
    echo "  run.sh help works"
else
    echo "FAIL: run.sh help did not produce expected output"
    exit 1
fi

# Check 7: Storage paths
VOICE_STORAGE="${VOICE_STORAGE:-/mnt/storage12tb/media/personas}"
if [[ ! -d "$VOICE_STORAGE" ]]; then
    echo "  INFO: Voice storage not found at $VOICE_STORAGE (12TB may not be mounted)"
else
    persona_count=$(ls -d "$VOICE_STORAGE"/*/ 2>/dev/null | wc -l)
    echo "  Voice storage found: $persona_count persona directories"
fi

# Check 8: Interview skill exists (used for voice design)
INTERVIEW_DIR="$(dirname "$SCRIPT_DIR")/interview"
if [[ -d "$INTERVIEW_DIR" ]]; then
    echo "  interview skill found (needed for design command)"
else
    echo "  INFO: interview skill not found at $INTERVIEW_DIR (design command may not work)"
fi

# Check 9: PersonaPlex cache path
PERSONAPLEX_CACHE="${PERSONAPLEX_CACHE:-$HOME/.cache/personaplex}"
if [[ -d "$PERSONAPLEX_CACHE" ]]; then
    echo "  PersonaPlex cache exists at $PERSONAPLEX_CACHE"
else
    echo "  INFO: PersonaPlex cache not yet created at $PERSONAPLEX_CACHE"
fi

echo "Result: PASS"
