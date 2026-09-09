#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
cmd="${1:-}"
if [ "$cmd" = "probe" ]; then shift; exec uv run --script scripts/scenario_probe.py "$@"; fi
exec uv run --script scripts/speak.py "$@"
