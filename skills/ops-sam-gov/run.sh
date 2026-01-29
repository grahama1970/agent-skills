#!/usr/bin/env bash
# SAM.gov Operations Skill Runner
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run the ops-sam-gov CLI
python "$SCRIPT_DIR/sam_gov_ops.py" "$@"
