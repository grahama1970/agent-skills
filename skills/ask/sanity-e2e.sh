#!/usr/bin/env bash
# Opt-in live sanity checks for /ask.
#
# This calls real composed skills and writes an HTML bug report. It is separate
# from sanity.sh because it can be slow, flaky, and cost-bearing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ " $* " == *" --help "* || " $* " == *" -h "* ]]; then
  exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/live_sanity_report.py" "$@"
fi

if [[ " $* " == *" --plan-only "* ]]; then
  exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/live_sanity_report.py" "$@"
fi

if [[ "${ASK_LIVE_SANITY_E2E:-0}" != "1" ]]; then
  echo "Refusing to run live E2E checks without ASK_LIVE_SANITY_E2E=1."
  echo "Example:"
  echo "  ASK_LIVE_SANITY_E2E=1 ./sanity-e2e.sh"
  echo ""
  echo "To render the planned report without executing live checks:"
  echo "  ./sanity-e2e.sh --plan-only"
  exit 2
fi

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/live_sanity_report.py" --allow-live "$@"
