#!/usr/bin/env bash
# Opt-in LIVE WebGPT transport gate for /surf.
#
# Calls real ./run.sh against Chrome + ChatGPT.
# Every WebGPT browser check uses --no-activate (background mode).
# Pytest transport_contract_only tests do NOT count as verified.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${SCRIPT_DIR}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi

if [[ " $* " == *" --help "* || " $* " == *" -h "* || " $* " == *" --plan-only "* ]]; then
  exec "$PYTHON" "$SCRIPT_DIR/scripts/live_webgpt_sanity.py" "$@"
fi

if [[ "${SURF_LIVE_WEBGPT_SANITY:-0}" != "1" ]]; then
  echo "Refusing live gate without SURF_LIVE_WEBGPT_SANITY=1."
  echo ""
  echo "All WebGPT checks run with --no-activate (background). You keep working in other tabs."
  echo ""
  echo "  SURF_LIVE_WEBGPT_SANITY=1 ./sanity-e2e.sh --profile release --url 'https://chatgpt.com/c/...'"
  echo "  SURF_LIVE_WEBGPT_SANITY=1 ./sanity-e2e.sh --profile smoke --tab-id TAB_ID"
  echo ""
  echo "Stress (failure modes): SURF_LIVE_WEBGPT_SANITY=1 ./sanity-e2e.sh --profile stress --tab-id TAB_ID"
  echo "Plan only: ./sanity-e2e.sh --plan-only --profile release|stress"
  exit 2
fi

exec "$PYTHON" "$SCRIPT_DIR/scripts/live_webgpt_sanity.py" --allow-live "$@"
