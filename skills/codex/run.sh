#!/bin/bash
# Use the python script
PYTHONPATH="${PYTHONPATH}:$(dirname "$0")" python3 "$(dirname "$0")/codex.py" "$@"
