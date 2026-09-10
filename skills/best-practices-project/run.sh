#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-verify}" in
  verify|sanity)
    exec "$SCRIPT_DIR/sanity.sh"
    ;;
  *)
    echo "Usage: $0 [verify|sanity]" >&2
    exit 2
    ;;
esac
