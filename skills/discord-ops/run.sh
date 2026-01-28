#!/usr/bin/env bash
# Discord Operations Skill Runner
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure we're using the skill's Python environment
cd "$SCRIPT_DIR"

# Run the discord-ops CLI
python discord_ops.py "$@"
