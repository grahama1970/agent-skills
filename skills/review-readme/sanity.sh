#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
python3 -m compileall -q review_readme.py
python3 -m pytest tests/ -q
./run.sh tests/fixtures/minimal_readme.md --skip-oracle --json >/dev/null
echo "sanity OK"
