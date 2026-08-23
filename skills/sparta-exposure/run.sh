#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-}" in
  check)
    shift
    exec python3 "$SCRIPT_DIR/scripts/validate_contract.py" "$@"
    ;;
  --help|-h|help|"")
    cat <<'EOF'
Usage:
  ./run.sh check [--json] [--scenario NAME] [--samples N] [--seed N]

Checks the SPARTA exposure skill contract. This is a local contract guard only;
it does not call live Memory, ArangoDB, monitor-sparta, or Sparta Explorer.
EOF
    ;;
  *)
    echo "unknown command: $1" >&2
    exit 2
    ;;
esac
