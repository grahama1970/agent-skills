#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ID="${RUN_ID:-oc-subagent-sanity-$(date +%Y%m%dT%H%M%S)}"
ARTIFACT_DIR="${ARTIFACT_DIR:-/tmp/oc-subagent/${RUN_ID}}"

export RUN_ID
export ARTIFACT_DIR
exec python3 "$SCRIPT_DIR/scripts/run_mvp_e2e.py"
