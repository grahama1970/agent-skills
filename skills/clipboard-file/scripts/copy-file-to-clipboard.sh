#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  copy-file-to-clipboard.sh [--target auto|kde|uri-list|gnome|gnome-copied-files] FILE

Copies FILE to the desktop clipboard as a file-manager paste item, not as plain text.
Verifies TARGETS and payload before exiting.
EOF
}

target="auto"
file_path=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      target="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "$file_path" ]]; then
        echo "Only one file path is supported." >&2
        exit 2
      fi
      file_path="$1"
      shift
      ;;
  esac
done

if [[ -z "$file_path" ]]; then
  usage >&2
  exit 2
fi

if ! command -v xclip >/dev/null 2>&1; then
  echo "ERROR: xclip is not installed or not on PATH." >&2
  echo "FALLBACK_PATH=$file_path"
  exit 1
fi

if [[ ! -e "$file_path" ]]; then
  echo "ERROR: file does not exist: $file_path" >&2
  exit 1
fi

abs_path="$(realpath -e "$file_path")"
uri="file://${abs_path}"

desktop="${XDG_CURRENT_DESKTOP:-}"
case "$target" in
  auto)
    if [[ "$desktop" == *KDE* ]]; then
      mime_target="text/uri-list"
      payload_mode="uri-list"
    elif [[ "$desktop" == *GNOME* ]]; then
      mime_target="x-special/gnome-copied-files"
      payload_mode="gnome"
    else
      mime_target="text/uri-list"
      payload_mode="uri-list"
    fi
    ;;
  kde|uri-list|text/uri-list)
    mime_target="text/uri-list"
    payload_mode="uri-list"
    ;;
  gnome|gnome-copied-files|x-special/gnome-copied-files)
    mime_target="x-special/gnome-copied-files"
    payload_mode="gnome"
    ;;
  *)
    echo "ERROR: unsupported target: $target" >&2
    usage >&2
    exit 2
    ;;
esac

pid_file="/tmp/codex-clipboard-file-${USER:-user}.pid"
log_file="/tmp/codex-clipboard-file-${USER:-user}.log"

old_pid=""
if [[ -f "$pid_file" ]]; then
  old_pid="$(cat "$pid_file" 2>/dev/null || true)"
fi

if [[ "$payload_mode" == "uri-list" ]]; then
  setsid sh -c 'printf "%s\r\n" "$1" | xclip -selection clipboard -t "$2" -loops 0' sh "$uri" "$mime_target" >"$log_file" 2>&1 &
else
  setsid sh -c 'printf "copy\n%s\n" "$1" | xclip -selection clipboard -t "$2" -loops 0' sh "$uri" "$mime_target" >"$log_file" 2>&1 &
fi
launcher_pid="$!"

sleep 0.35

targets="$(xclip -selection clipboard -t TARGETS -o 2>/dev/null | tr '\0' '\n' || true)"
payload="$(xclip -selection clipboard -t "$mime_target" -o 2>/dev/null || true)"
owner_pid="$(pgrep -n -f "xclip -selection clipboard -t ${mime_target} -loops 0" || true)"

if ! printf '%s\n' "$targets" | grep -Fxq "$mime_target"; then
  echo "ERROR: clipboard TARGETS did not include $mime_target" >&2
  echo "TARGETS:"
  printf '%s\n' "$targets"
  echo "FALLBACK_PATH=$abs_path"
  exit 1
fi

if ! printf '%s' "$payload" | grep -Fq "$uri"; then
  echo "ERROR: clipboard payload did not contain expected URI." >&2
  echo "TARGET=$mime_target"
  echo "EXPECTED_URI=$uri"
  echo "PAYLOAD:"
  printf '%s\n' "$payload"
  echo "FALLBACK_PATH=$abs_path"
  exit 1
fi

if [[ -z "$owner_pid" ]] || ! ps -p "$owner_pid" >/dev/null 2>&1; then
  echo "ERROR: clipboard owner process is not alive for target: $mime_target" >&2
  echo "LAUNCHER_PID=$launcher_pid" >&2
  echo "FALLBACK_PATH=$abs_path"
  exit 1
fi

echo "$owner_pid" > "$pid_file"

if [[ -n "$old_pid" && "$old_pid" =~ ^[0-9]+$ && "$old_pid" != "$owner_pid" ]]; then
  kill "$old_pid" >/dev/null 2>&1 || true
fi

echo "OK clipboard file copy verified"
echo "TARGET=$mime_target"
echo "URI=$uri"
echo "OWNER_PID=$owner_pid"
echo "TARGETS:"
printf '%s\n' "$targets"
