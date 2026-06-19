#!/usr/bin/env bash

surf_webgpt_lock_file() {
  printf '%s\n' "${SURF_WEBGPT_LOCK_FILE:-/tmp/surf-webgpt-submit.lock}"
}

surf_webgpt_lock_timeout() {
  printf '%s\n' "${SURF_WEBGPT_LOCK_TIMEOUT:-0}"
}

surf_webgpt_acquire_lock() {
  local lock_file lock_timeout
  lock_file="$(surf_webgpt_lock_file)"
  lock_timeout="$(surf_webgpt_lock_timeout)"
  mkdir -p "$(dirname "$lock_file")"
  exec {SURF_WEBGPT_LOCK_FD}>"$lock_file"
  if [[ "$lock_timeout" == "0" ]]; then
    if ! flock -n "$SURF_WEBGPT_LOCK_FD"; then
      return 73
    fi
  else
    if ! flock -w "$lock_timeout" "$SURF_WEBGPT_LOCK_FD"; then
      return 73
    fi
  fi
  printf 'pid=%s\nstarted_at=%s\ncommand=%s\n' "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&"$SURF_WEBGPT_LOCK_FD"
  return 0
}

surf_webgpt_release_lock() {
  if [[ -n "${SURF_WEBGPT_LOCK_FD:-}" ]]; then
    flock -u "$SURF_WEBGPT_LOCK_FD" 2>/dev/null || true
  fi
}
