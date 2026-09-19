#!/usr/bin/env bash
# Deterministic sanity by default; a key alone never authorizes a live call.
set -euo pipefail
cd "$(dirname "$0")"
uv run --project . --extra test python -m pytest -q
node --experimental-strip-types --test tests/*.test.ts
if [[ "${1:-}" == "--live" ]]; then
  ./run.sh ask --questions '{"probe":{"type":"noul","instructions":"Does the state explicitly identify itself as a synthetic probe?"}}' \
    --state '{"note":"synthetic probe"}' --allow-egress
fi
