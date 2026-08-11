#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() {
  cat <<'EOF'
Usage: run.sh --offline-fixtures [--out DIR]

Runs the pinned noncanonical CocoIndex-vs-native incremental evaluation against
copied fixtures. The command fails closed if the exact CocoIndex package is not
present or if either arm does not run.
EOF
}

OUT_DIR=""
MODE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --offline-fixtures)
      MODE="offline-fixtures"
      shift
      ;;
    --out)
      OUT_DIR="${2:?--out requires a directory}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$MODE" != "offline-fixtures" ]]; then
  usage >&2
  exit 2
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for the eval-only CocoIndex environment" >&2
  exit 2
fi

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -z "$OUT_DIR" ]]; then
  OUT_DIR="$SCRIPT_DIR/reports/$RUN_ID"
fi
mkdir -p "$OUT_DIR/cache" "$OUT_DIR/tmp" "$OUT_DIR/xdg"

export HOME="$OUT_DIR/home"
export XDG_CACHE_HOME="$OUT_DIR/xdg/cache"
export XDG_CONFIG_HOME="$OUT_DIR/xdg/config"
export XDG_DATA_HOME="$OUT_DIR/xdg/data"
export TMPDIR="$OUT_DIR/tmp"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$OUT_DIR/cache/pycache"
export PYTHONPATH="$SKILL_DIR"

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/prove_cocoindex_incremental.py" \
  --out "$OUT_DIR"
