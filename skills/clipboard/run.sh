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

recover_desktop_env() {
  if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
    return 0
  fi

  local user_name proc env_file name key value
  user_name="${USER:-$(id -un)}"

  for name in plasmashell kwin_x11 gnome-shell; do
    while IFS= read -r proc; do
      env_file="/proc/${proc}/environ"
      [[ -r "$env_file" ]] || continue

      while IFS='=' read -r key value; do
        case "$key" in
          DISPLAY|WAYLAND_DISPLAY|XAUTHORITY|XDG_SESSION_TYPE|XDG_CURRENT_DESKTOP|DBUS_SESSION_BUS_ADDRESS)
            [[ -n "$value" ]] && export "$key=$value"
            ;;
        esac
      done < <(tr '\0' '\n' < "$env_file")

      if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
        return 0
      fi
    done < <(pgrep -u "$user_name" -x "$name" 2>/dev/null || true)
  done

  if [[ -z "${DISPLAY:-}" && -S /tmp/.X11-unix/X0 ]]; then
    export DISPLAY=:0
    if [[ -z "${XAUTHORITY:-}" && -r "/run/user/$(id -u)/.Xauthority" ]]; then
      export XAUTHORITY="/run/user/$(id -u)/.Xauthority"
    fi
  fi
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
    recover_desktop_env
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
