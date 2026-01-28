#!/usr/bin/env bash
# DARPA Operations Skill Runner
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run the darpa-ops CLI
python "$SCRIPT_DIR/darpa_ops.py" "$@"
