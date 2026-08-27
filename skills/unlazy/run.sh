#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'USAGE'
Usage: skills/unlazy/run.sh <command> [args...]

Commands:
  gate-check [args...]       Run scripts/gate-check.mjs
  gate-lint [args...]        Run scripts/gate-lint.mjs
  dispatch-check [args...]   Run scripts/dispatch-check.mjs
  install-hooks [args...]    Run scripts/install-hooks.mjs
  stop-hook [args...]        Run scripts/stop-hook.mjs
  test                       Run the upstream npm test suite
  sanity                     Run the local sanity checks
USAGE
}

cmd="${1:-}"
if [[ -n "$cmd" ]]; then
  shift
fi

case "$cmd" in
  gate-check)
    exec node "$SCRIPT_DIR/scripts/gate-check.mjs" "$@"
    ;;
  gate-lint)
    exec node "$SCRIPT_DIR/scripts/gate-lint.mjs" "$@"
    ;;
  dispatch-check)
    exec node "$SCRIPT_DIR/scripts/dispatch-check.mjs" "$@"
    ;;
  install-hooks)
    exec node "$SCRIPT_DIR/scripts/install-hooks.mjs" "$@"
    ;;
  stop-hook)
    exec node "$SCRIPT_DIR/scripts/stop-hook.mjs" "$@"
    ;;
  test)
    cd "$SCRIPT_DIR"
    exec npm test
    ;;
  sanity)
    exec "$SCRIPT_DIR/sanity.sh"
    ;;
  ""|help|--help|-h)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
