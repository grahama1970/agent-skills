#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
cmd="${1:-}"; shift || true
case "$cmd" in
  build) exec uv run --with pydantic --with typer python scripts/create_kling_scene.py "$@" ;;
  *) echo "usage: run.sh build --scene <table.json> --refs name=/path.png ... --out-dir <dir>" >&2; exit 2 ;;
esac
