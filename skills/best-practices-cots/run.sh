#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-}" in
  scan)
    shift
    node "$SCRIPT_DIR/scanner.cjs" "$@"
    ;;
  *)
    echo "Usage: ./run.sh scan <url> [--manifest <file>] [--plan] [--rules C01,C02] [--json]"
    ;;
esac
