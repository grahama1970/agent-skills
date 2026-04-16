#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [review-persona] Sanity Check ==="

# Check 1: Required files exist
echo "Check 1: Required files..."
for f in SKILL.md run.sh src/cli.py src/review.py src/__init__.py; do
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

# Check 3: Python imports
if python3 -c "import typer" 2>/dev/null; then
    echo "  typer available"
else
    echo "FAIL: typer not installed"
    exit 1
fi

if python3 -c "import yaml" 2>/dev/null; then
    echo "  pyyaml available"
else
    echo "FAIL: pyyaml not installed"
    exit 1
fi

# Check 4: Source files are parseable
for pyfile in src/cli.py src/review.py; do
    if ! python3 -c "import ast; ast.parse(open('$SCRIPT_DIR/$pyfile').read())" 2>/dev/null; then
        echo "FAIL: $pyfile has syntax errors"
        exit 1
    fi
done
echo "  Python source files parse without errors"

# Check 5: Module import works
cd "$SCRIPT_DIR"
if python3 -c "
import sys
sys.path.insert(0, '.')
from src.review import load_persona_yaml
" 2>/dev/null; then
    echo "  Module import OK"
else
    echo "  WARN: Could not import review module (may need venv)"
fi

# Check 6: Quick check with a test persona YAML
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

cat > "$TMPDIR/test_persona.yaml" << 'YAML'
name: Test Persona
type: fictional
age: 25
role: engineer
voice_references:
  - actor: Test Actor
    register: confident
    weight: 1.0
domain: cybersecurity
media_consumption:
  podcasts: ["Test Podcast"]
  movies: ["Test Movie"]
YAML

if python3 -c "
import yaml
with open('$TMPDIR/test_persona.yaml') as f:
    data = yaml.safe_load(f)
assert data['name'] == 'Test Persona', 'YAML loading failed'
assert 'voice_references' in data, 'Missing voice_references'
print('  Test persona YAML loads correctly')
" 2>&1; then
    : # output printed by python
else
    echo "FAIL: Test persona YAML processing failed"
    exit 1
fi

# Check 7: Personas storage (non-blocking)
PERSONAS_DIR="/mnt/storage12tb/media/personas"
if [[ -d "$PERSONAS_DIR" ]]; then
    persona_count=$(ls -d "$PERSONAS_DIR"/*/ 2>/dev/null | wc -l)
    echo "  Found $persona_count personas in $PERSONAS_DIR"
else
    echo "  INFO: Personas storage not found at $PERSONAS_DIR (12TB may not be mounted)"
fi

echo "Result: PASS"
