#!/bin/bash
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

show_help() {
  cat <<'HELP'
png-svg-converter

Usage:
  ./run.sh check
  ./run.sh convert <input.png> --output <output.svg> [options]

Options:
  --threshold <percent>      Threshold for binarization (default: 50%)
  --mode <fill|stroke>       SVG render mode (default: fill)
  --color <value>            Fill/stroke color (default: currentColor)
  --stroke-width <value>     Stroke width in stroke mode (default: 1.5)
  --background <value>       transparent or CSS color (default: transparent)

Examples:
  ./run.sh check
  ./run.sh convert ./icon.png --output ./icon.svg
  ./run.sh convert ./icon.png --output ./icon.svg --mode stroke --stroke-width 1.4
HELP
}

if [ $# -eq 0 ]; then
  show_help
  exit 1
fi

case "${1:-}" in
  -h|--help)
    show_help
    exit 0
    ;;
esac

exec "$PYTHON_BIN" "$SCRIPT_DIR/scripts/convert.py" "$@"
