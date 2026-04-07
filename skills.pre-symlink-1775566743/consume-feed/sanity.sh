#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== consume-feed Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh cli.py feed_config.py feed_runner.py feed_storage.py pyproject.toml; do
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

# Check 3: Python dependencies importable
echo -n "Check 3: Python dependencies... "
if ! python3 -c "import typer; import rich; import httpx; import feedparser; import pydantic; import yaml" 2>/dev/null; then
    echo "FAIL: Missing Python deps (typer, rich, httpx, feedparser, pydantic, pyyaml)"
    echo "  Run: cd $SCRIPT_DIR && uv sync"
    exit 1
fi
echo "OK"

# Check 4: /memory reachable
echo -n "Check 4: /memory... "
MEMORY_RUN="$(cd "$(dirname "${BASH_SOURCE[0]}")/../memory" && pwd)/run.sh"
if ! "$MEMORY_RUN" count --collection lessons 2>/dev/null; then
    echo "WARN (/memory not reachable, storage features will fail)"
else
    echo "OK"
fi

# Check 5: Feed config module loads
echo -n "Check 5: feed_config module... "
if ! PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 -c "from feed_config import FeedConfig, SourceType" 2>/dev/null; then
    echo "FAIL: feed_config module broken"
    exit 1
fi
echo "OK"

# Check 6: CLI help works (via uv)
echo -n "Check 6: CLI help... "
if ! cd "$SCRIPT_DIR" && uv run python -m cli --help >/dev/null 2>&1; then
    echo "FAIL: 'uv run python -m cli --help' failed"
    exit 1
fi
echo "OK"

# Check 7: Config directory exists
echo -n "Check 7: configs directory... "
if [[ ! -d "$SCRIPT_DIR/configs" ]]; then
    echo "FAIL: configs/ directory missing"
    exit 1
fi
echo "OK"

echo "Result: PASS"
