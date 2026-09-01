#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cmd="${1:-help}"
shift || true
case "$cmd" in
  check-contract)
    exec python3 "$SCRIPT_DIR/scripts/check_contract.py" "$@"
    ;;
  verify|test)
    exec "$SCRIPT_DIR/sanity.sh" "$@"
    ;;
  help|-h|--help)
    cat <<'EOF'
Usage: ./run.sh <command>

Commands:
  check-contract   Validate SKILL.md preserves required Chatterbox guidance
  verify           Run sanity.sh
EOF
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    exit 2
    ;;
esac
