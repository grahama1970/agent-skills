#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== train-persona Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh pyproject.toml scripts/__init__.py scripts/train_persona.py scripts/upgrade_traces.py; do
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

# Check 3: usage output works (run.sh prints usage on no args, exits 1)
echo -n "Check 3: usage output... "
USAGE_OUT=$("$SCRIPT_DIR/run.sh" 2>&1 || true)
if echo "$USAGE_OUT" | grep -q "train-persona"; then
    echo "OK"
else
    echo "FAIL: run.sh produced no usage output"
    exit 1
fi

# Check 4: uv available
echo -n "Check 4: uv available... "
if ! command -v uv >/dev/null 2>&1; then
    echo "FAIL: uv not found"
    exit 1
fi
echo "OK"

# Check 5: Core Python deps (torch, transformers, peft)
echo -n "Check 5: ML dependencies... "
if ! python3 -c "import torch" 2>/dev/null; then
    echo "SKIP (torch not installed; training requires GPU setup)"
else
    TORCH_VER=$(python3 -c "import torch; print(torch.__version__)" 2>/dev/null)
    CUDA=$(python3 -c "import torch; print('CUDA' if torch.cuda.is_available() else 'CPU')" 2>/dev/null)
    echo "OK (torch $TORCH_VER, $CUDA)"
fi

# Check 6: transformers + peft + trl
echo -n "Check 6: HuggingFace stack... "
if ! python3 -c "import transformers; import peft; import trl" 2>/dev/null; then
    echo "SKIP (transformers/peft/trl not installed; run 'cd $SCRIPT_DIR && uv sync')"
else
    echo "OK"
fi

# Check 7: typer + rich (CLI deps)
echo -n "Check 7: CLI dependencies... "
if ! python3 -c "import typer; import rich; import pydantic" 2>/dev/null; then
    echo "FAIL: Missing CLI deps (typer, rich, pydantic)"
    exit 1
fi
echo "OK"

# Check 8: train_persona.py syntax valid
echo -n "Check 8: train_persona.py syntax... "
if ! python3 -c "import ast; ast.parse(open('$SCRIPT_DIR/scripts/train_persona.py').read())" 2>/dev/null; then
    echo "FAIL: train_persona.py has syntax errors"
    exit 1
fi
echo "OK"

# Check 9: /create-persona skill reachable
echo -n "Check 9: create-persona skill... "
CREATE_PERSONA="$SCRIPT_DIR/../create-persona"
if [[ -d "$CREATE_PERSONA" ]] && [[ -f "$CREATE_PERSONA/SKILL.md" ]]; then
    echo "OK"
else
    echo "WARN (create-persona skill not found; generate --source create-persona will fail)"
fi

echo "Result: PASS"
