#!/bin/bash
# Entry point for the context skill
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
python3 "$SCRIPT_DIR/handoff.py" "$@"
