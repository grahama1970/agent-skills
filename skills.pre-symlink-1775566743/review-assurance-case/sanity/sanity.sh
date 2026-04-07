#!/usr/bin/env bash
# Sanity check for review-assurance-case skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== review-assurance-case sanity check ==="

# 1. Python imports work
echo -n "Checking imports... "
cd "$SKILL_DIR"
uv run --project "$SKILL_DIR" python -c "
from config import CHECKS, PROVIDERS, CATEGORY_WEIGHTS
assert len(CHECKS) == 55, f'Expected 55 checks, got {len(CHECKS)}'
assert len(PROVIDERS) == 4, f'Expected 4 providers, got {len(PROVIDERS)}'
assert len(CATEGORY_WEIGHTS) == 7, f'Expected 7 categories, got {len(CATEGORY_WEIGHTS)}'
from prompts import STEP1_PROMPT, STEP2_PROMPT, STEP3_PROMPT
assert '{case_content}' in STEP1_PROMPT
from providers import find_provider_cli, run_provider_async
from review_assurance_case import app
print('OK')
"

# 2. CLI help works
echo -n "Checking CLI help... "
uv run --project "$SKILL_DIR" python "$SKILL_DIR/review_assurance_case.py" --help > /dev/null 2>&1
echo "OK"

# 3. Checks command works
echo -n "Checking 'checks' command... "
uv run --project "$SKILL_DIR" python "$SKILL_DIR/review_assurance_case.py" checks --category structural > /dev/null 2>&1
echo "OK"

# 4. Check command works
echo -n "Checking 'check' command... "
output=$(uv run --project "$SKILL_DIR" python "$SKILL_DIR/review_assurance_case.py" check 2>/dev/null)
echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'provider' in d" 2>/dev/null
echo "OK"

# 5. Models command works
echo -n "Checking 'models' command... "
output=$(uv run --project "$SKILL_DIR" python "$SKILL_DIR/review_assurance_case.py" models 2>/dev/null)
echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'github' in d" 2>/dev/null
echo "OK"

echo "=== All sanity checks passed ==="
