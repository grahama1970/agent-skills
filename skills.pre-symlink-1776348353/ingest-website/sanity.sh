#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PASS=0
FAIL=0

check() {
  local desc="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "  PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $desc"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== ingest-website sanity ==="
cd "$SCRIPT_DIR"

# 1. Python deps importable
check "httpx importable" uv run python -c "import httpx"
check "beautifulsoup4 importable" uv run python -c "from bs4 import BeautifulSoup"
check "typer importable" uv run python -c "import typer"
check "loguru importable" uv run python -c "from loguru import logger"

# 2. CLI help works
check "CLI --help" uv run python ingest_website.py --help

# 3. Composed skills exist
check "/fetcher exists" test -f "$SKILLS_ROOT/fetcher/run.sh"
check "/extractor exists" test -f "$SKILLS_ROOT/extractor/run.sh"
check "/doc2qra exists" test -f "$SKILLS_ROOT/doc2qra/run.sh"
check "/memory exists" test -f "$SKILLS_ROOT/memory/run.sh"
check "/taxonomy exists" test -f "$SKILLS_ROOT/taxonomy/run.sh"
check "/embedding exists" test -f "$SKILLS_ROOT/embedding/run.sh"

# 4. Required files present
check "SKILL.md present" test -f "$SCRIPT_DIR/SKILL.md"
check "run.sh present" test -f "$SCRIPT_DIR/run.sh"
check "run.sh executable" test -x "$SCRIPT_DIR/run.sh"
check "pyproject.toml present" test -f "$SCRIPT_DIR/pyproject.toml"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
