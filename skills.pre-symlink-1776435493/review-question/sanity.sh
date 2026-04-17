#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== review-question sanity ==="

# 1. Imports resolve
echo -n "Import check... "
uv run --project "$SCRIPT_DIR" python -c "from review_question import app; print('OK')"

# 2. Help text renders
echo -n "Help text... "
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/review_question.py" --help >/dev/null 2>&1 && echo "OK" || echo "FAIL"

# 3. Config loads
echo -n "Config check... "
uv run --project "$SCRIPT_DIR" python -c "from config import PERSONAS, F36_CATEGORIES; print(f'OK ({len(PERSONAS)} personas, {len(F36_CATEGORIES)} categories)')"

# 4. Validators load
echo -n "Validators check... "
uv run --project "$SCRIPT_DIR" python -c "from validators import validate_question; print('OK')"

# 5. Generators load
echo -n "Generators check... "
uv run --project "$SCRIPT_DIR" python -c "from generators import generate_questions; print('OK')"

# 6. Conversation module loads
echo -n "Conversation check... "
uv run --project "$SCRIPT_DIR" python -c "from conversation import execute_conversation; print('OK')"

echo "=== sanity complete ==="
