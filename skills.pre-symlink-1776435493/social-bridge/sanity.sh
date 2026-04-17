#!/usr/bin/env bash
# Social Bridge Sanity Check
# Verifies the modular structure is working correctly.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() { echo -e "${GREEN}PASS${NC}: $1"; }
fail() { echo -e "${RED}FAIL${NC}: $1"; exit 1; }
warn() { echo -e "${YELLOW}WARN${NC}: $1"; }

echo "=== Social Bridge Sanity Check ==="
echo ""

# Use conda python if available, otherwise system python
PYTHON="${CONDA_PYTHON:-/home/graham/miniconda3/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="python3"
fi

echo "Using Python: $PYTHON"
echo ""

# 1. Check all module files exist
echo "--- Checking module files ---"
MODULES=(
    "social_bridge/__init__.py"
    "social_bridge/config.py"
    "social_bridge/utils.py"
    "social_bridge/telegram.py"
    "social_bridge/twitter.py"
    "social_bridge/discord_webhook.py"
    "social_bridge/graph_storage.py"
    "social_bridge/cli_commands.py"
    "social_bridge.py"
)

for module in "${MODULES[@]}"; do
    if [[ -f "$module" ]]; then
        pass "File exists: $module"
    else
        fail "Missing file: $module"
    fi
done

# 2. Check line counts (all modules < 500 lines)
echo ""
echo "--- Checking line counts (must be < 500) ---"
MAX_LINES=500
for module in "${MODULES[@]}"; do
    lines=$(wc -l < "$module")
    if (( lines < MAX_LINES )); then
        pass "$module: $lines lines"
    else
        fail "$module: $lines lines (exceeds $MAX_LINES)"
    fi
done

# 3. Check Python syntax for all modules
echo ""
echo "--- Checking Python syntax ---"
for module in "${MODULES[@]}"; do
    if "$PYTHON" -m py_compile "$module" 2>/dev/null; then
        pass "Syntax OK: $module"
    else
        fail "Syntax error in: $module"
    fi
done

# 4. Check imports (no circular imports)
echo ""
echo "--- Checking imports (no circular dependencies) ---"
PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH" "$PYTHON" -c "
import sys
sys.path.insert(0, '.')

# Test importing each module in order
try:
    from social_bridge import config
    print('  config.py: OK')
except ImportError as e:
    print(f'  config.py: FAIL - {e}')
    sys.exit(1)

try:
    from social_bridge import utils
    print('  utils.py: OK')
except ImportError as e:
    print(f'  utils.py: FAIL - {e}')
    sys.exit(1)

try:
    from social_bridge import telegram
    print('  telegram.py: OK')
except ImportError as e:
    print(f'  telegram.py: FAIL - {e}')
    sys.exit(1)

try:
    from social_bridge import twitter
    print('  twitter.py: OK')
except ImportError as e:
    print(f'  twitter.py: FAIL - {e}')
    sys.exit(1)

try:
    from social_bridge import discord_webhook
    print('  discord_webhook.py: OK')
except ImportError as e:
    print(f'  discord_webhook.py: FAIL - {e}')
    sys.exit(1)

try:
    from social_bridge import graph_storage
    print('  graph_storage.py: OK')
except ImportError as e:
    print(f'  graph_storage.py: FAIL - {e}')
    sys.exit(1)

try:
    from social_bridge import cli_commands
    print('  cli_commands.py: OK')
except ImportError as e:
    print(f'  cli_commands.py: FAIL - {e}')
    sys.exit(1)

# Test the package init
try:
    import social_bridge
    print('  __init__.py: OK')
    print(f'  Version: {social_bridge.__version__}')
except ImportError as e:
    print(f'  __init__.py: FAIL - {e}')
    sys.exit(1)

print('All imports successful - no circular dependencies')
" && pass "Import check passed" || fail "Import check failed"

# 5. Check CLI entry point can be loaded
echo ""
echo "--- Checking CLI entry point ---"
PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH" "$PYTHON" -c "
import sys
sys.path.insert(0, '.')

# Try importing the main CLI module
try:
    # We can't fully import it without typer/rich, but we can check it parses
    import ast
    with open('social_bridge.py', 'r') as f:
        ast.parse(f.read())
    print('CLI entry point parses correctly')
except SyntaxError as e:
    print(f'CLI syntax error: {e}')
    sys.exit(1)
" && pass "CLI entry point OK" || fail "CLI entry point failed"

# 6. Check for key exports from modules
echo ""
echo "--- Checking module exports ---"
PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH" "$PYTHON" -c "
import sys
sys.path.insert(0, '.')

from social_bridge.utils import SocialPost, RateLimiter, with_retries, extract_security_tags
from social_bridge.config import DATA_DIR, CONFIG_FILE, SECURITY_KEYWORDS
from social_bridge.telegram import TELETHON_AVAILABLE, fetch_channels_sync
from social_bridge.discord_webhook import HTTPX_AVAILABLE, send_to_webhook
from social_bridge.graph_storage import persist_to_memory, search_memory
print('Key exports available from modules')
" && pass "Module exports OK" || fail "Module exports failed"

# 7. Verify monolith backup exists
echo ""
echo "--- Checking monolith backup ---"
if [[ -f "social_bridge_monolith.py" ]]; then
    monolith_lines=$(wc -l < "social_bridge_monolith.py")
    pass "Monolith backup exists: social_bridge_monolith.py ($monolith_lines lines)"
else
    warn "Monolith backup not found (optional)"
fi

# Summary
echo ""
echo "=== Sanity Check Complete ==="
echo -e "${GREEN}All checks passed!${NC}"
