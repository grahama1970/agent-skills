#!/usr/bin/env bash
set -euo pipefail

DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

if (($# == 0)); then
  echo \
    "usage: $0 validate|list|ask|sample|cockpit-proof|cockpit|validate-proof|interaction-manifest|debugger-source-reveal-receipt|debugger-runtime-proof-receipt|excalidraw-proposal-receipt ..." \
    >&2
  exit 2
fi

cmd=$1
shift

case "$cmd" in
  validate|list|ask|sample|cockpit-proof|cockpit|validate-proof|interaction-manifest|debugger-source-reveal-receipt|debugger-runtime-proof-receipt|excalidraw-proposal-receipt)
    PYTHONPATH="$DIR/scripts" \
      uv run \
      --isolated \
      --with pydantic \
      --with typer \
      --with httpx \
      --with loguru \
      python3 "$DIR/scripts/explain_project.py" \
      "$cmd" "$@"
    ;;
  *)
    echo \
      "usage: $0 validate|list|ask|sample|cockpit-proof|cockpit|validate-proof|interaction-manifest|debugger-source-reveal-receipt|debugger-runtime-proof-receipt|excalidraw-proposal-receipt ..." \
      >&2
    exit 2
    ;;
esac
