#!/usr/bin/env bash
# goal-drift entrypoint. Read-only auditor.
unset VIRTUAL_ENV
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
run_python() {
  if command -v uv >/dev/null 2>&1; then
    [ -d "$ROOT/.venv" ] || uv venv "$ROOT/.venv" --quiet
    uv pip install --python "$ROOT/.venv/bin/python" --quiet typer >/dev/null 2>&1 || true
    PYTHONPATH="$ROOT/src" "$ROOT/.venv/bin/python" -m goal_drift.cli "$@"
  else
    PYTHONPATH="$ROOT/src" python3 -m goal_drift.cli "$@"
  fi
}
cmd="${1:-help}"; shift || true
case "$cmd" in
  register|goal|check|schedule) run_python "$cmd" "$@" ;;
  sanity) "$ROOT/sanity.sh" ;;
  help|-h|--help) run_python --help ;;
  *) echo "Unknown command: $cmd (register goal check schedule sanity)" >&2; exit 2 ;;
esac
