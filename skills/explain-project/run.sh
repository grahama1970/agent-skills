#!/usr/bin/env bash
set -euo pipefail

DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

usage="usage: $0 validate|list|ask|sample|scaffold|milestone|answer-question|cockpit-proof|cockpit|validate-proof|validate-deploy|eval-browser-sync|eval-interview-cockpit-path|interaction-manifest|debugger-source-reveal-receipt|debugger-runtime-proof-receipt|excalidraw-proposal-receipt ..."

if (($# == 0)); then
  echo "$usage" >&2
  exit 2
fi

cmd=$1
shift

case "$cmd" in
  bridge)
    PYTHONPATH="$DIR/scripts" uv run --isolated --with pydantic --with typer --with httpx --with loguru \
      python3 -m explain_project_core.execution "$@"
    ;;
  eval-browser-sync)
    uv run --isolated --with httpx python3 "$DIR/scripts/eval_browser_sync.py" "$@"
    ;;
  eval-bridge-execution)
    uv run --isolated --with httpx python3 "$DIR/scripts/eval_bridge_execution.py" "$@"
    ;;
  eval-interview-cockpit-path)
    uv run --isolated --with pydantic --with typer --with httpx --with loguru python3 "$DIR/scripts/eval_interview_cockpit_path.py" "$@"
    ;;
  validate-deploy)
    python3 "$DIR/scripts/validate_deploy.py" "$@"
    ;;
  validate|list|ask|sample|scaffold|milestone|answer-question|cockpit-proof|cockpit|validate-proof|interaction-manifest|debugger-source-reveal-receipt|debugger-runtime-proof-receipt|excalidraw-proposal-receipt)
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
    echo "$usage" >&2
    exit 2
    ;;
esac
