#!/bin/bash
set -euo pipefail
# Hack Skill Entry Point

# Ensure the script directory is in PYTHONPATH so we can import modules if needed
export PYTHONPATH="${PYTHONPATH-}:$(dirname "$0")"

# Execute the python CLI
exec python3 "$(dirname "$0")/hack.py" "$@"
