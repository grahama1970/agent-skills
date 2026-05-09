#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
COPY_FILE_SCRIPT="$ROOT_DIR/clipboard-file/scripts/copy-file-to-clipboard.sh"

usage() {
  cat <<'EOF'
Usage:
  run.sh file [--target auto|kde|uri-list|gnome|gnome-copied-files] FILE
  run.sh text TEXT

File mode copies FILE as a desktop file-list clipboard item and verifies the
MIME target. KDE Plasma uses text/uri-list.
EOF
}

mode="${1:-}"
if [[ -z "$mode" ]]; then
  usage >&2
  exit 2
fi
shift

case "$mode" in
  file)
    exec "$COPY_FILE_SCRIPT" "$@"
    ;;
  text)
    if [[ $# -lt 1 ]]; then
      usage >&2
      exit 2
    fi
    if ! command -v xclip >/dev/null 2>&1; then
      echo "ERROR: xclip is not installed or not on PATH." >&2
      exit 1
    fi
    printf '%s' "$*" | xclip -selection clipboard
    payload="$(xclip -selection clipboard -o 2>/dev/null || true)"
    if [[ "$payload" != "$*" ]]; then
      echo "ERROR: clipboard text verification failed" >&2
      exit 1
    fi
    echo "OK clipboard text copy verified"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "ERROR: unknown mode: $mode" >&2
    usage >&2
    exit 2
    ;;
esac
