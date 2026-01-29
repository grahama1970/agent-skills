#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Readarr Ops Skill Sanity ==="

# 1. Check file structure
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [PASS] run.sh exists and is executable"
else
    echo "  [FAIL] run.sh missing or not executable"
    exit 1
fi

if [[ -f "$SCRIPT_DIR/readarr_ops.py" ]]; then
    echo "  [PASS] readarr_ops.py exists"
else
    echo "  [FAIL] readarr_ops.py missing"
    exit 1
fi

# 2. Check Python Configuration
if command -v python3 >/dev/null 2>&1; then
    echo "  [PASS] python3 is available"
else
    echo "  [FAIL] python3 not found"
    exit 1
fi

# Check imports (requests, typer, rich)
if python3 -c "import requests, typer, rich" 2>/dev/null; then
    echo "  [PASS] Required Python modules (requests, typer, rich) are installed"
else
    echo "  [FAIL] Missing Python modules. Run: pip install requests typer rich"
    exit 1
fi

# 3. Check CLI basic execution
if "$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1; then
    echo "  [PASS] run.sh --help works"
else
    echo "  [FAIL] run.sh --help failed"
    exit 1
fi

# 4. Check Environment Variables (Warning only)
# Source .env if exists to be fair
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

if [[ -n "$READARR_API_KEY" ]]; then
    echo "  [PASS] READARR_API_KEY is set"
else
    echo "  [WARN] READARR_API_KEY is NOT set. Live commands will fail."
fi

if [[ -n "$NZBD_GEEK_API_KEY" ]]; then
    echo "  [PASS] NZBD_GEEK_API_KEY is set"
else
    echo "  [WARN] NZBD_GEEK_API_KEY is NOT set. NZB search will fail."
fi

echo ""
echo "Result: PASS"
