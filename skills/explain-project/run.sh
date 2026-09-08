#!/usr/bin/env bash
set -euo pipefail

DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

if (($# == 0)); then
  echo \
    "usage: $0 validate|list|ask|sample|cockpit-proof|cockpit|validate-proof ..." \
    >&2
  exit 2
fi

cmd=$1
shift

case "$cmd" in
  validate|list|ask|sample|cockpit-proof|cockpit|validate-proof)
    PYTHONPATH="$DIR/scripts" \
      uv run \
      --with pydantic \
      --with typer \
      --with httpx \
      --with loguru \
      python3 "$DIR/scripts/explain_project.py" \
      "$cmd" "$@"
    ;;
  *)
    echo \
      "usage: $0 validate|list|ask|sample|cockpit-proof|cockpit|validate-proof ..." \
      >&2
    exit 2
    ;;
esac
