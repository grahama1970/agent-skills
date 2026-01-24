#!/usr/bin/env bash
# Entry point for the cleanup skill
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
python3 "$SCRIPT_DIR/cleanup.py" "$@"
