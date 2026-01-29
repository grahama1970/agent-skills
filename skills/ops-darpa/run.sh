#!/usr/bin/env bash
# DARPA Operations Skill Runner
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run the ops-darpa CLI
python "$SCRIPT_DIR/darpa_ops.py" "$@"
