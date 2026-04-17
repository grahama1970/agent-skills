#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [create-ksml] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh adapter.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL - missing $f"
        exit 1
    fi
done
echo "OK"

# Check 2: uv available
echo -n "Check 2: uv available... "
if ! command -v uv &>/dev/null; then
    echo "FAIL - uv not found"
    exit 1
fi
echo "OK"

# Check 3: Python imports (pyyaml, typer)
echo -n "Check 3: Python imports (yaml, typer)... "
if ! python3 -c "import yaml; import typer; print('OK', end='')" 2>/dev/null; then
    echo "FAIL - missing pyyaml or typer"
    exit 1
fi
echo ""

# Check 4: adapter.py syntax valid
echo -n "Check 4: adapter.py syntax... "
if ! python3 -c "import py_compile; py_compile.compile('$SCRIPT_DIR/adapter.py', doraise=True)" 2>/dev/null; then
    echo "FAIL - syntax error in adapter.py"
    exit 1
fi
echo "OK"

# Check 5: Smoke test - generate KSML from minimal script
echo -n "Check 5: Smoke test (minimal KSML generation)... "
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

# Create minimal test script
cat > "$TMPDIR/test_script.json" << 'EOF'
{
    "title": "Sanity Test",
    "style": "Cinematic",
    "scenes": [
        {
            "visual": "A dark room",
            "action": ["Character enters"],
            "shot_type": "wide",
            "duration_seconds": 5,
            "emotion": "tense"
        }
    ]
}
EOF
mkdir -p "$TMPDIR/assets"

# Run the adapter convert command
cd "$SCRIPT_DIR"
uv run --script "$SCRIPT_DIR/adapter.py" convert \
    --script "$TMPDIR/test_script.json" \
    --assets "$TMPDIR/assets" \
    --output "$TMPDIR/output" 2>/dev/null

if [[ -f "$TMPDIR/output/kling_export/project.ksml" ]]; then
    echo "OK"
else
    echo "FAIL - KSML file not generated"
    exit 1
fi

echo "Result: PASS"
