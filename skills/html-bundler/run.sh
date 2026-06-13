#!/usr/bin/env bash
set -euo pipefail

unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SURF_BIN="${SURF_BIN:-$SKILLS_ROOT/surf/run.sh}"
FETCHER_BIN="${FETCHER_BIN:-$SKILLS_ROOT/fetcher/run.sh}"
CLIPBOARD_BIN="$SKILLS_ROOT/clipboard/run.sh"
PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
  cat <<'USAGE'
html-bundler

Usage:
  ./run.sh capture (--html PATH | --url URL) [options]
  ./run.sh capture ... --clipboard

Defaults:
  --out       /tmp/html-bundler-<timestamp>.zip
  --surf-bin  skills/surf/run.sh

Examples:
  ./run.sh capture --html ./public/index.html --root ./public
  ./run.sh capture --url http://localhost:3000 --root ./public --source-entry index.html
  ./run.sh capture --url http://localhost:3000 --clipboard
  ./run.sh capture --html ./index.html --out /tmp/my-page.zip
USAGE
}

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 2
fi

cmd="${1:-}"
shift

case "$cmd" in
  capture)
    clipboard=0
    args=()
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --clipboard)
          clipboard=1
          shift
          ;;
        -h|--help)
          usage
          exit 0
          ;;
        *)
          args+=("$1")
          shift
          ;;
      esac
    done

    if [[ ! -e "$SURF_BIN" ]]; then
      echo "error: surf entrypoint not found: $SURF_BIN" >&2
      echo "Run: $SKILLS_ROOT/surf/sanity.sh" >&2
      exit 1
    fi

    zip_path="$("$PYTHON_BIN" "$SCRIPT_DIR/scripts/cli.py" "${args[@]}" --surf-bin "$SURF_BIN" --fetcher-bin "$FETCHER_BIN")"
    echo "$zip_path"

    if [[ "$clipboard" -eq 1 ]]; then
      if [[ ! -e "$CLIPBOARD_BIN" ]]; then
        echo "error: clipboard entrypoint not found: $CLIPBOARD_BIN" >&2
        exit 1
      fi
      exec "$CLIPBOARD_BIN" file "$zip_path"
    fi
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/scripts/cli.py" "$cmd" "$@"
    ;;
esac
