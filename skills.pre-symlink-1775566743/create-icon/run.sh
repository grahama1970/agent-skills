#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# run.sh - Entry point for icon-creator skill
#
# Usage:
#   ./run.sh fetch <icon-name> --name <output-name> [--active-color "#HEX"]
#   ./run.sh generate <path> --name <output-name> [--active-color "#HEX"]
#   ./run.sh list
#
# Examples:
#   ./run.sh fetch folder --name my_folder
#   ./run.sh fetch play --name play_btn --active-color "#FF6600"
#   ./run.sh generate ./custom.svg --name custom --dir ./icons

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

function show_help() {
    cat << 'EOF'
Icon Creator - Stream Deck icon generation tool

Usage:
  ./run.sh fetch <icon-name> --name <output> [options]
  ./run.sh generate <path> --name <output> [options]
  ./run.sh list

Commands:
  fetch <name>     Fetch icon from Lucide CDN (https://lucide.dev)
  generate <path>  Generate states from local SVG/PNG file
  list             List popular Lucide icon names

Options:
  --name NAME           Output filename (required, no extension)
  --dir DIR             Output directory (default: ./icon)
  --active-color HEX    Active state color (default: #00FFFF cyan)

Examples:
  ./run.sh fetch folder --name folder_icon
  ./run.sh fetch volume-2 --name volume --active-color "#FF9900"
  ./run.sh generate ./logo.svg --name company_logo
  ./run.sh list

Output:
  Creates two files in the target directory:
    - {name}_white.png  (inactive state)
    - {name}_active.png (active state, colored)

Both files are 72x72 PNG with transparent background.
EOF
}

# Check for help flag anywhere in args
for arg in "$@"; do
    case "$arg" in
        -h|--help)
            show_help
            exit 0
            ;;
    esac
done

# No args = show help
if [ $# -eq 0 ]; then
    show_help
    exit 1
fi

# Pass all arguments to Python script
exec python3 "$SKILL_DIR/creator.py" "$@"
