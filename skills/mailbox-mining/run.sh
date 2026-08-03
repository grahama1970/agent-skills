#!/usr/bin/env bash
# ops-gmail entrypoint. Strip inherited venv (cross-skill subprocess safety).
unset VIRTUAL_ENV
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
run_python() {
  if command -v uv >/dev/null 2>&1; then
    if [ ! -d "$ROOT/.venv" ]; then uv venv "$ROOT/.venv" --quiet; fi
    uv pip install --python "$ROOT/.venv/bin/python" --quiet typer httpx jsonschema >/dev/null 2>&1 || true
    "$ROOT/.venv/bin/python" "$@"
  else
    python3 "$@"
  fi
}
cmd="${1:-help}"; shift || true
case "$cmd" in
  redact|mine|draft-validate|assess|outbox) run_python "$ROOT/scripts/cli.py" "$cmd" "$@" ;;
  sanity) "$ROOT/sanity.sh" ;;
  help|-h|--help) run_python "$ROOT/scripts/cli.py" --help ;;
  *) echo "Unknown command: $cmd (try: auth-status redact mine draft-validate assess sanity)" >&2; exit 2 ;;
esac
