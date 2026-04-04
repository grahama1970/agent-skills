#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SKILL_DIR"

echo "=== sanity: review-prompt ==="

# 1. Python compiles
python3 -c "import ast; ast.parse(open('review_prompt.py').read()); print('  compile: OK')"

# 2. CLI help works
uv run python review_prompt.py --help > /dev/null 2>&1 && echo "  cli: OK" || echo "  cli: FAIL"

# 3. Dry run with a test prompt
TEMP=$(mktemp /tmp/test_prompt_XXXX.txt)
echo "You are a helpful assistant. {placeholder}" > "$TEMP"
uv run python review_prompt.py --template "$TEMP" --dry-run > /dev/null 2>&1 && echo "  dry-run: OK" || echo "  dry-run: FAIL"
rm -f "$TEMP"

echo "=== sanity: PASS ==="
