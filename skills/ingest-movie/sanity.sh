#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Testing ingest-movie modular CLI..."

# Core CLI
"$SCRIPT_DIR"/run.sh --help >/dev/null && echo "✓ main --help"

# Scenes subcommands
"$SCRIPT_DIR"/run.sh scenes find --help >/dev/null && echo "✓ scenes find --help"
"$SCRIPT_DIR"/run.sh scenes extract --help >/dev/null && echo "✓ scenes extract --help"
"$SCRIPT_DIR"/run.sh scenes analyze --help >/dev/null && echo "✓ scenes analyze --help"
"$SCRIPT_DIR"/run.sh scenes quality --help >/dev/null && echo "✓ scenes quality --help"

# Batch subcommands
"$SCRIPT_DIR"/run.sh batch discover --help >/dev/null && echo "✓ batch discover --help"
"$SCRIPT_DIR"/run.sh batch plan --help >/dev/null && echo "✓ batch plan --help"
"$SCRIPT_DIR"/run.sh batch status --help >/dev/null && echo "✓ batch status --help"

# Agent subcommands
"$SCRIPT_DIR"/run.sh agent recommend --help >/dev/null && echo "✓ agent recommend --help"
"$SCRIPT_DIR"/run.sh agent quick --help >/dev/null && echo "✓ agent quick --help"
"$SCRIPT_DIR"/run.sh agent discover --help >/dev/null && echo "✓ agent discover --help"
"$SCRIPT_DIR"/run.sh agent inventory --help >/dev/null && echo "✓ agent inventory --help"

# Subs subcommands
"$SCRIPT_DIR"/run.sh subs download --help >/dev/null && echo "✓ subs download --help"

# Acquire subcommands
"$SCRIPT_DIR"/run.sh acquire radarr --help >/dev/null && echo "✓ acquire radarr --help"
"$SCRIPT_DIR"/run.sh acquire preset --help >/dev/null && echo "✓ acquire preset --help"

echo ""
echo "✅ All sanity checks passed!"
