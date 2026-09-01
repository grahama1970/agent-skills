#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/best-practices-fastapi-venv}"
case "${1:-}" in
  convert-to-flask)
    shift
    uv run --no-project --with pydantic --with flask python "$SCRIPT_DIR/scripts/convert_to_flask.py" "$@"
    ;;
  sanity)
    shift || true
    bash "$SCRIPT_DIR/sanity.sh" "$@"
    ;;
  *)
    echo "Usage: $0 {convert-to-flask|sanity}" >&2
    exit 2
    ;;
esac
