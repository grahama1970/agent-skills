#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="${1:-readonly}"
"$SCRIPT_DIR/run.sh" auth status --profile "$PROFILE" --validate
"$SCRIPT_DIR/run.sh" profile --profile "$PROFILE"
echo "gmail live sanity: PASS ($PROFILE)"
