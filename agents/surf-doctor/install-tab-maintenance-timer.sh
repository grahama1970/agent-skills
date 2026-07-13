#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SYSTEMD_DIR="${SCRIPT_DIR}/systemd"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
CADENCE="${SURF_TAB_MAINTENANCE_CADENCE:-30min}"
RANDOMIZED_DELAY="${SURF_TAB_MAINTENANCE_RANDOMIZED_DELAY:-5min}"
RUNTIME_MAX_SEC="${SURF_TAB_MAINTENANCE_RUNTIME_MAX_SEC:-120}"
TIMEOUT_SECONDS="${SURF_TAB_MAINTENANCE_TIMEOUT:-15}"
RECEIPT_DIR="${SURF_TAB_MAINTENANCE_RECEIPT_DIR:-${XDG_STATE_HOME:-${HOME}/.local/state}/surf/tab-maintenance-receipts}"
TAB_MAINTENANCE_SCRIPT="${SURF_TAB_MAINTENANCE_SCRIPT:-${REPO_ROOT}/skills/surf/scripts/tab-maintenance.sh}"
ENABLE=0
START=0

usage() {
  cat <<'EOF'
Usage: install-tab-maintenance-timer.sh [--enable] [--start]

Installs user-level systemd unit files for Surf Doctor proactive tab maintenance.
The installer is idempotent and does not enable or start the timer unless asked.

Environment overrides:
  SURF_TAB_MAINTENANCE_CADENCE            Default: 30min
  SURF_TAB_MAINTENANCE_RANDOMIZED_DELAY   Default: 5min
  SURF_TAB_MAINTENANCE_RUNTIME_MAX_SEC    Default: 120
  SURF_TAB_MAINTENANCE_TIMEOUT            Default: 15
  SURF_TAB_MAINTENANCE_RECEIPT_DIR        Default: $XDG_STATE_HOME/surf/tab-maintenance-receipts
  SURF_TAB_MAINTENANCE_SCRIPT             Default: repo skills/surf/scripts/tab-maintenance.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable) ENABLE=1; shift ;;
    --start) START=1; shift ;;
    --install|install) shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

escape_sed_replacement() {
  printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'
}

render_unit() {
  local src="$1" dst="$2"
  local cadence randomized_delay runtime_max timeout receipt script
  cadence="$(escape_sed_replacement "$CADENCE")"
  randomized_delay="$(escape_sed_replacement "$RANDOMIZED_DELAY")"
  runtime_max="$(escape_sed_replacement "$RUNTIME_MAX_SEC")"
  timeout="$(escape_sed_replacement "$TIMEOUT_SECONDS")"
  receipt="$(escape_sed_replacement "$RECEIPT_DIR")"
  script="$(escape_sed_replacement "$TAB_MAINTENANCE_SCRIPT")"
  sed \
    -e "s|@CADENCE@|${cadence}|g" \
    -e "s|@RANDOMIZED_DELAY@|${randomized_delay}|g" \
    -e "s|@RUNTIME_MAX_SEC@|${runtime_max}|g" \
    -e "s|@TIMEOUT_SECONDS@|${timeout}|g" \
    -e "s|@RECEIPT_DIR@|${receipt}|g" \
    -e "s|@TAB_MAINTENANCE_SCRIPT@|${script}|g" \
    "$src" > "$dst.tmp"
  if [[ -f "$dst" ]] && cmp -s "$dst.tmp" "$dst"; then
    rm -f "$dst.tmp"
  else
    mv "$dst.tmp" "$dst"
  fi
}

mkdir -p "$USER_SYSTEMD_DIR" "$RECEIPT_DIR"
render_unit "$SYSTEMD_DIR/surf-tab-maintenance.service" "$USER_SYSTEMD_DIR/surf-tab-maintenance.service"
render_unit "$SYSTEMD_DIR/surf-tab-maintenance.timer" "$USER_SYSTEMD_DIR/surf-tab-maintenance.timer"

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload || true
  if [[ "$ENABLE" -eq 1 ]]; then
    systemctl --user enable surf-tab-maintenance.timer
  fi
  if [[ "$START" -eq 1 ]]; then
    systemctl --user start surf-tab-maintenance.timer
  fi
fi

printf 'Installed %s and %s\n' \
  "$USER_SYSTEMD_DIR/surf-tab-maintenance.service" \
  "$USER_SYSTEMD_DIR/surf-tab-maintenance.timer"
