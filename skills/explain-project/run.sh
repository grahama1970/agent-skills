#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cmd=${1:-}
shift || true
case "$cmd" in
  validate|list|ask|sample)
    uv run --with pydantic python3 "$DIR/scripts/explain_project.py" "$cmd" "$@"
    ;;
  *)
    echo "usage: $0 validate|list|ask|sample ..." >&2
    exit 2
    ;;
esac
